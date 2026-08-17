import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from django.core.cache import cache
from django.db.models import Count, Sum
from django.utils import timezone
from apps.administrations.repositories import (
    AnnouncementBannerRepository,
    CancellationPolicyRepository,
    LegalDocumentRepository,
    OfferRepository,
    PopularRentalRepository,
    PlatformConfigRepository,
    TaxRateRepository,
)
from apps.administrations.models import (
    CancellationTier,
    LegalDocument,
    TaxRate,
)


class CancellationPolicyService:

    @staticmethod
    def _auto_label(min_h: int, max_h: int | None) -> str:
        if max_h is None:
            return f"More than {min_h} hours before pickup"
        if min_h == 0:
            return f"Less than {max_h} hours before pickup"
        return f"{min_h} – {max_h} hours before pickup"

    @staticmethod
    def _auto_description(refund: float) -> str:
        if refund == 100:
            return "Full refund of advance payment."
        if refund == 0:
            return "No refund."
        return f"{refund}% refund of advance payment."

    @staticmethod
    def _build_rules(policy, payment_mode: str) -> list[dict]:
        tiers = sorted(
            (t for t in policy.tiers.all() if t.payment_mode == payment_mode),
            key=lambda t: -t.min_hours_before_pickup,
        )
        rules = []
        for tier in tiers:
            min_h = tier.min_hours_before_pickup
            max_h = tier.max_hours_before_pickup
            # Decimal → float, rounded to 2dp to avoid binary float
            # artifacts (e.g. 33.33 rendering as 33.330000000000005).
            refund = round(float(tier.refund_percentage), 2)
            rules.append(
                {
                    "hours_before_pickup": min_h,
                    "refund_percentage": refund,
                    "label": tier.label
                    or CancellationPolicyService._auto_label(min_h, max_h),
                    "description": tier.description
                    or CancellationPolicyService._auto_description(refund),
                }
            )
        return rules

    @staticmethod
    def get_current_policy() -> dict | None:
        policy = CancellationPolicyRepository.get_current()
        if policy is None:
            return None

        return {
            "full_payment_rules": CancellationPolicyService._build_rules(
                policy, CancellationTier.PaymentMode.FULL
            ),
            "partial_payment_rules": CancellationPolicyService._build_rules(
                policy, CancellationTier.PaymentMode.PARTIAL
            ),
            "note": policy.refund_note,
        }


class OfferService:

    @staticmethod
    def get_offers() -> list:
        """
        Returns active offers with is_featured annotated on the first item
        (lowest sort_order). The serializer reads this boolean so the
        frontend knows which card gets the yellow styling.
        """
        offers = list(OfferRepository.get_active_offers())
        for idx, offer in enumerate(offers):
            offer.is_featured = idx == 0
        return offers


class PopularRentalService:

    @staticmethod
    def get_popular_rentals(city_id: int) -> list:
        """
        Returns active PopularRental objects for the given city with
        resolved_name and resolved_image annotated so the serializer
        never branches on optional override fields.
        """
        rentals = list(PopularRentalRepository.get_active_by_city(city_id))
        for rental in rentals:
            vt = rental.vehicle_type
            rental.resolved_name = rental.display_name or vt.name
            rental.resolved_image = rental.display_image or vt.primary_image or None
            rental.resolved_pickup_location = rental.pickup_location
        return rentals


class AnnouncementBannerService:
    @staticmethod
    def get_current_banner(page: str):
        return AnnouncementBannerRepository.get_current_for_page(page)


class PlatformConfigService:
    """
    Typed accessor for PlatformConfig. Every getter falls back to the
    given default if the key doesn't exist, or if the stored value
    can't be parsed as the requested type (e.g. an admin fat-fingers a
    non-numeric string into an INTEGER-typed key) — a bad config value
    should never take checkout down, it should just silently fall back.
    """

    @staticmethod
    def get_int(key: str, default: int) -> int:
        config = PlatformConfigRepository.get_by_key(key)
        if config is None:
            return default
        try:
            return int(config.value)
        except (TypeError, ValueError):
            return default

    # @staticmethod
    # def get_int(key: str, default: int) -> int:
    #     cache_key = f"platform_config:{key}"
    #     cached = cache.get(cache_key)
    #     if cached is not None:
    #         return cached
    #     config = PlatformConfigRepository.get_by_key(key)
    #     value = int(config.value) if config else default
    #     cache.set(
    #         cache_key, value, timeout=300
    #     )  # 5 min TTL — admin changes propagate within 5 min
    #     return value

    @staticmethod
    def get_decimal(key: str, default: Decimal) -> Decimal:
        config = PlatformConfigRepository.get_by_key(key)
        if config is None:
            return default
        try:
            return Decimal(config.value)
        except (TypeError, ValueError, InvalidOperation):
            return default

    @staticmethod
    def get_bool(key: str, default: bool) -> bool:
        config = PlatformConfigRepository.get_by_key(key)
        if config is None:
            return default
        return config.value.strip().lower() in ("true", "1", "yes")

    @staticmethod
    def get_str(key: str, default: str) -> str:
        config = PlatformConfigRepository.get_by_key(key)
        return config.value if config is not None else default

    @staticmethod
    def get_json(key: str, default):
        config = PlatformConfigRepository.get_by_key(key)
        if config is None:
            return default
        try:
            return json.loads(config.value)
        except (TypeError, ValueError):
            return default


class LegalDocumentService:

    @staticmethod
    def get_current(doc_type: str):
        return LegalDocumentRepository.get_current(doc_type)


class TaxCalculationService:
    """
    Single source of truth for tax math — used by both the pre-checkout
    preview (VehicleDetailService) and actual order creation
    (BookingCheckoutService), so the number shown before payment can
    never drift from what's actually charged.

    Returns rate=None cleanly (percentage/amount both 0) when no
    TaxRate row exists for a context yet — same fail-safe philosophy as
    PlatformConfigService: missing config should never break checkout.
    """

    @staticmethod
    def get_vendor_rental_tax(rent_amount: Decimal) -> dict:
        rate = TaxRateRepository.get_current(TaxRate.Context.VENDOR_RENTAL)
        percentage = rate.percentage if rate else Decimal("0")
        amount = (rent_amount * percentage / Decimal("100")).quantize(Decimal("0.01"))
        return {"rate": rate, "percentage": percentage, "amount": amount}

    @staticmethod
    def get_commission_tax(commission_amount: Decimal) -> dict:
        rate = TaxRateRepository.get_current(TaxRate.Context.PLATFORM_COMMISSION)
        percentage = rate.percentage if rate else Decimal("0")
        amount = (commission_amount * percentage / Decimal("100")).quantize(
            Decimal("0.01")
        )
        return {"rate": rate, "percentage": percentage, "amount": amount}

    @staticmethod
    def build_snapshot(vendor_tax: dict, commission_tax: dict) -> dict:
        """Freezes rate content itself, not just the FK — same reasoning
        as _build_vendor_terms_snapshot / _build_platform_tc_snapshot."""

        def _freeze(tax):
            rate = tax["rate"]
            if rate is None:
                return None
            return {
                "version": rate.version,
                "name": rate.name,
                "percentage": str(rate.percentage),
                "cgst_percentage": str(rate.cgst_percentage),
                "sgst_percentage": str(rate.sgst_percentage),
                "igst_percentage": str(rate.igst_percentage),
                "hsn_sac_code": rate.hsn_sac_code,
                "amount": str(tax["amount"]),
            }

        return {
            "vendor_rental_tax": _freeze(vendor_tax),
            "platform_commission_tax": _freeze(commission_tax),
        }


def _trend_pct(current, previous) -> float:
    if not previous:
        return 100.0 if current else 0.0
    return round(float((current - previous) / previous * 100), 1)


class AdminDashboardService:

    @staticmethod
    def _month_bounds():
        now = timezone.localtime()
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if this_month_start.month == 1:
            last_month_start = this_month_start.replace(
                year=this_month_start.year - 1, month=12
            )
        else:
            last_month_start = this_month_start.replace(
                month=this_month_start.month - 1
            )
        return this_month_start, now, last_month_start, this_month_start

    @staticmethod
    def get_dashboard():
        from apps.vendors.models import Vendor
        from apps.vehicles.models import VehicleListing
        from apps.bookings.models import Booking
        from apps.payments.models import VendorPayout
        from apps.users.models import User, Role

        this_start, now, last_start, last_end = AdminDashboardService._month_bounds()

        # Platform's own commission revenue — deliberately NOT vendor
        # gross revenue. Bucketed by returned_at (the moment a trip
        # actually finished), same reasoning as the vendor dashboard's
        # equivalent metric.
        revenue_this_month = Booking.objects.filter(
            status=Booking.Status.COMPLETED,
            returned_at__gte=this_start,
            returned_at__lt=now,
        ).aggregate(total=Sum("net_commission_amount"))["total"] or Decimal("0")
        revenue_last_month = Booking.objects.filter(
            status=Booking.Status.COMPLETED,
            returned_at__gte=last_start,
            returned_at__lt=last_end,
        ).aggregate(total=Sum("net_commission_amount"))["total"] or Decimal("0")

        bookings_this_month = Booking.objects.filter(
            created_at__gte=this_start, created_at__lt=now
        ).count()
        bookings_last_month = Booking.objects.filter(
            created_at__gte=last_start, created_at__lt=last_end
        ).count()

        weekly_bars = []
        today = timezone.localdate()
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
            end = start + timedelta(days=1)
            weekly_bars.append(
                Booking.objects.filter(
                    created_at__gte=start, created_at__lt=end
                ).count()
            )

        vendors_this_month = Vendor.objects.filter(
            created_at__gte=this_start, created_at__lt=now
        ).count()
        vendors_last_month = Vendor.objects.filter(
            created_at__gte=last_start, created_at__lt=last_end
        ).count()

        status_rows = Booking.objects.values("status").annotate(count=Count("id"))
        booking_status_counts = {row["status"]: row["count"] for row in status_rows}

        pending_payouts = VendorPayout.objects.filter(
            status=VendorPayout.Status.PENDING
        )
        pending_payout_amount = pending_payouts.aggregate(total=Sum("total_amount"))[
            "total"
        ] or Decimal("0")

        total_customers = (
            User.objects.exclude(
                role_assignments__role__system_role__in=[
                    Role.SystemRole.VENDOR,
                    Role.SystemRole.SUPPORT,
                    Role.SystemRole.SUPER_ADMIN,
                ]
            )
            .distinct()
            .count()
        )

        return {
            "pending_vendor_approvals": Vendor.objects.filter(
                status=Vendor.Status.PENDING
            ).count(),
            "pending_listing_approvals": VehicleListing.objects.filter(
                status=VehicleListing.Status.PENDING_APPROVAL
            ).count(),
            "revenue_this_month": revenue_this_month,
            "revenue_last_month": revenue_last_month,
            "revenue_trend_pct": _trend_pct(revenue_this_month, revenue_last_month),
            "bookings_this_month": bookings_this_month,
            "bookings_last_month": bookings_last_month,
            "bookings_trend_pct": _trend_pct(bookings_this_month, bookings_last_month),
            "weekly_booking_bars": weekly_bars,
            "active_vendors": Vendor.objects.filter(
                status=Vendor.Status.APPROVED
            ).count(),
            "vendors_this_month": vendors_this_month,
            "vendors_last_month": vendors_last_month,
            "vendors_trend_pct": _trend_pct(vendors_this_month, vendors_last_month),
            "total_customers": total_customers,
            "booking_status_counts": booking_status_counts,
            "pending_payout_amount": pending_payout_amount,
            "pending_payout_count": pending_payouts.count(),
            "recent_bookings": Booking.objects.select_related(
                "listing__vendor", "listing__vehicle_type__brand", "customer"
            ).order_by("-created_at")[:5],
            "range_label": f"{this_start:%d %b %Y} - {now:%d %b %Y}",
        }
