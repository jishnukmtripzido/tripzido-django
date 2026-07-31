# apps/vendors/repositories.py
from apps.vendors.models import VendorTerms
from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Q, Sum
from django.utils import timezone
from apps.bookings.models import Booking
from apps.payments.models import VendorPayout
from apps.vehicles.models import VehicleListing, ListingBlockedPeriod


class VendorTermsRepository:

    @staticmethod
    def get_current(vendor_id: int):
        return VendorTerms.objects.filter(vendor_id=vendor_id, is_current=True).first()

    @staticmethod
    def save_new_version(vendor_id: int, data: dict) -> VendorTerms:
        """
        Reuses VendorTerms.save()'s own versioning logic rather than
        reimplementing it: fetching the current row (if any) and
        mutating its fields before calling .save() triggers the
        "if self.pk is not None" branch on the model, which bumps
        version, detaches the pk, and inserts a brand-new row — so
        this never overwrites history, only adds to it. A vendor's
        first-ever save (no current row yet) falls through to a fresh
        VendorTerms(vendor_id=...) instance instead, which the model's
        own save() already handles correctly (stays at version=1).
        """
        current = VendorTerms.objects.filter(
            vendor_id=vendor_id, is_current=True
        ).first()
        terms = current or VendorTerms(vendor_id=vendor_id)
        for field, value in data.items():
            setattr(terms, field, value)
        terms.save()
        return terms


class VendorDashboardRepository:

    @staticmethod
    def get_current_balance(vendor_id: int) -> Decimal:
        """
        "You're owed" — broader definition per your call: every FULL/
        COMPLETED booking not yet fully paid out, whether or not staff
        have batched it into a VendorPayout yet. Covers both "not
        attached to any payout" and "attached, but that payout hasn't
        been marked PAID."
        """
        total = (
            Booking.objects.filter(
                listing__vendor_id=vendor_id,
                payment_mode=Booking.PaymentMode.FULL,
                status=Booking.Status.COMPLETED,
            )
            .filter(
                Q(payout_item__isnull=True)
                | ~Q(payout_item__payout__status=VendorPayout.Status.PAID)
            )
            .aggregate(total=Sum("net_amount"))["total"]
        )
        return total or Decimal("0")

    @staticmethod
    def get_revenue_for_period(vendor_id: int, start, end) -> Decimal:
        """Completed-trip revenue only, bucketed by returned_at — the
        actual moment a trip finished, not when it was booked."""
        total = Booking.objects.filter(
            listing__vendor_id=vendor_id,
            status=Booking.Status.COMPLETED,
            returned_at__gte=start,
            returned_at__lt=end,
        ).aggregate(total=Sum("net_amount"))["total"]
        return total or Decimal("0")

    @staticmethod
    def get_orders_count_for_period(vendor_id: int, start, end) -> int:
        """Any booking placed in the period, any status — bucketed by
        created_at, not trip completion."""
        return Booking.objects.filter(
            listing__vendor_id=vendor_id,
            created_at__gte=start,
            created_at__lt=end,
        ).count()

    @staticmethod
    def get_weekly_booking_counts(vendor_id: int) -> list[int]:
        """Last 7 days including today, oldest first — feeds the bar
        chart. 7 small queries; fine for a dashboard, not a hot path."""
        today = timezone.localdate()
        counts = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
            end = start + timedelta(days=1)
            counts.append(
                Booking.objects.filter(
                    listing__vendor_id=vendor_id,
                    created_at__gte=start,
                    created_at__lt=end,
                ).count()
            )
        return counts

    @staticmethod
    def get_needs_attention(vendor_id: int, limit: int = 5):
        """
        (bookings to start, bookings to mark returned). "To start" =
        CONFIRMED with pickup_date already here or passed. "To return"
        = ONGOING with dropoff_date already here or passed. Both are
        real vendor actions already wired via VendorBookingService's
        existing status-transition endpoint.
        """
        today = timezone.localdate()
        to_start = (
            Booking.objects.filter(
                listing__vendor_id=vendor_id,
                status=Booking.Status.CONFIRMED,
                pickup_date__lte=today,
            )
            .select_related(
                "listing__vehicle_type",
                "pickup_location",
                "customer",
                "pricing_package__package_type",
            )
            .order_by("pickup_date")[:limit]
        )
        to_return = (
            Booking.objects.filter(
                listing__vendor_id=vendor_id,
                status=Booking.Status.ONGOING,
                dropoff_date__lte=today,
            )
            .select_related(
                "listing__vehicle_type",
                "pickup_location",
                "customer",
                "pricing_package__package_type",
            )
            .order_by("dropoff_date")[:limit]
        )
        return to_start, to_return

    @staticmethod
    def get_fleet_snapshot(vendor_id: int) -> dict:
        total = VehicleListing.objects.filter(vendor_id=vendor_id).count()
        pending_approval = VehicleListing.objects.filter(
            vendor_id=vendor_id, status=VehicleListing.Status.PENDING_APPROVAL
        ).count()
        now = timezone.now()
        blocked_units = (
            ListingBlockedPeriod.objects.filter(
                listing__vendor_id=vendor_id,
                start_datetime__lte=now,
                end_datetime__gte=now,
            ).aggregate(total=Sum("count"))["total"]
            or 0
        )
        return {
            "total_listings": total,
            "pending_approval": pending_approval,
            "blocked_units": blocked_units,
        }

    @staticmethod
    def get_recent_bookings(vendor_id: int, limit: int = 5):
        return (
            Booking.objects.filter(listing__vendor_id=vendor_id)
            .select_related(
                "listing__vehicle_type",
                "pickup_location",
                "customer",
                "pricing_package__package_type",
            )
            .order_by("-created_at")[:limit]
        )
