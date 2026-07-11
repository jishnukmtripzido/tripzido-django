import uuid
import secrets
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from apps.bookings.models import Booking, BookingCancellation
from apps.payments.models import Payment
from apps.bookings.cashfree_client import CashfreeClient
from apps.vehicles.repositories import VehicleDetailRepository
from apps.vehicles.services import AvailabilityService, VehicleDetailService
from django.conf import settings
from apps.bookings.models import Booking
from apps.bookings.repositories import BookingRepository, BookingCancellationRepository
from apps.administrations.repositories import CancellationPolicyRepository
from apps.administrations.services import (
    CancellationPolicyService,
    PlatformConfigService,
)
from apps.vendors.models import VendorTerms, VendorSubscription

from apps.administrations.models import CancellationTier
from apps.administrations.models import CustomerTCAcceptance
from apps.administrations.models import LegalDocument
from apps.administrations.repositories import LegalDocumentRepository
from apps.administrations.models import CancellationPolicy
from apps.vehicles.models import VehicleListing  # for type clarity only


def _generate_booking_reference() -> str:
    return "TRZ" + secrets.token_hex(4).upper()


def _generate_unique_booking_reference(max_attempts: int = 5) -> str:
    """
    Retries a few times on the rare chance _generate_booking_reference()
    collides with an existing row. Raises if it still can't find a free
    one after max_attempts — at that point something is wrong (e.g. the
    random space is exhausted, which shouldn't realistically happen at
    2^32 combinations, or there's a deeper DB issue).
    """
    for _ in range(max_attempts):
        candidate = _generate_booking_reference()
        if not Booking.objects.filter(booking_reference=candidate).exists():
            return candidate
    raise RuntimeError(
        "Could not generate a unique booking reference after "
        f"{max_attempts} attempts."
    )


def _generate_order_id() -> str:
    return "bk_" + uuid.uuid4().hex[:20]


class BookingCheckoutService:

    @staticmethod
    def _build_cancellation_snapshot(policy) -> dict:
        """
        Freezes the raw tier ranges for BOTH payment-mode schedules
        (FULL and PARTIAL) — not filtered to the booking's own mode —
        so _resolve_refund_percentage can later re-run the exact same
        range-matching logic against frozen data. Returns {} if there's
        no current policy at all.
        """
        if policy is None:
            return {}

        tiers = []
        for tier in policy.tiers.all():
            tiers.append(
                {
                    "payment_mode": tier.payment_mode,
                    "min_hours_before_pickup": tier.min_hours_before_pickup,
                    "max_hours_before_pickup": tier.max_hours_before_pickup,
                    "refund_percentage": str(tier.refund_percentage),
                }
            )

        return {
            "policy_version": policy.version,
            "policy_note": policy.refund_note,
            "tiers": tiers,
        }

    @staticmethod
    def _build_vendor_terms_snapshot(vendor_terms) -> dict:
        """
        Freezes the vendor terms content itself (not just the FK) —
        belt-and-suspenders in case VendorTerms is ever mutated via a
        queryset .update() that bypasses save()'s versioning logic.
        """
        if vendor_terms is None:
            return {}

        return {
            "version": vendor_terms.version,
            "terms_items": vendor_terms.terms_items,
            "security_deposit_note": vendor_terms.security_deposit_note,
            "operating_hours_note": vendor_terms.operating_hours_note,
            "distance_limit_note": vendor_terms.distance_limit_note,
            "excess_charge_note": vendor_terms.excess_charge_note,
            "late_penalty_note": vendor_terms.late_penalty_note,
        }

    @staticmethod
    def _build_platform_tc_snapshot(legal_doc) -> dict:
        """Freezes platform T&C content itself, same reasoning as above."""
        if legal_doc is None:
            return {}

        return {
            "version": legal_doc.version,
            "content": legal_doc.content,
        }

    @staticmethod
    @transaction.atomic
    def create_order(
        customer,
        listing_id: int,
        package_id: int,
        pickup_dt,
        dropoff_dt,
        quantity: int,
        payment_mode: str,
        return_url: str,
        ip_address: str | None = None,
    ) -> tuple[dict | None, str | None]:
        """
        Validates availability/pricing, creates N Booking rows (one per
        vehicle) + one Payment row, then creates the matching Cashfree
        order. Returns (result, None) on success or (None, error) if
        validation fails before any Cashfree call is made.

        The listing row is locked (select_for_update) for the duration of
        this transaction so two concurrent requests for the same listing
        can't both pass the capacity check for the same dates and create
        overlapping bookings that exceed the fleet size.
        """
        listing = VehicleDetailRepository.get_listing_for_checkout(listing_id)
        if listing is None:
            return None, "Vehicle listing not found"

        if listing.available_count <= 0:
            return None, "This vehicle is sold out at this location"

        if quantity < 1:
            return None, "Quantity must be at least 1"
        if quantity > listing.available_count:
            return None, "Requested quantity exceeds availability"

        is_available, message = AvailabilityService.is_available(
            listing.schedule_template_id, pickup_dt, dropoff_dt
        )
        if not is_available:
            return None, message

        remaining_capacity = AvailabilityService.get_remaining_capacity(
            listing.available_count, listing_id, pickup_dt, dropoff_dt
        )
        if quantity > remaining_capacity:
            return None, "Requested quantity exceeds availability for these dates"

        all_packages = list(listing.pricing_packages.all())
        duration_hours = AvailabilityService.compute_duration_hours(
            pickup_dt, dropoff_dt
        )
        applicable = AvailabilityService.get_applicable_packages(
            all_packages, duration_hours
        )
        match = next((p for p in applicable if p[0].pk == package_id), None)
        if match is None:
            return None, "Selected package is not valid for this booking duration"

        pkg, multiplier = match
        unit_rent_amount = pkg.price * multiplier

        commission_percentage, partial_allowed = (
            VehicleDetailService._get_vendor_commission_info(listing.vendor)
        )
        commission_percentage = Decimal(str(commission_percentage or 0))
        can_pay_partial = bool(
            pkg.pay_at_pickup_enabled and partial_allowed and commission_percentage > 0
        )

        requested_mode = payment_mode if payment_mode in ("FULL", "PARTIAL") else "FULL"
        effective_mode = (
            requested_mode
            if (requested_mode != "PARTIAL" or can_pay_partial)
            else "FULL"
        )

        if effective_mode == "PARTIAL":
            unit_advance = (
                unit_rent_amount * commission_percentage / Decimal("100")
            ).quantize(Decimal("0.01"))
        else:
            unit_advance = unit_rent_amount
        unit_remaining = unit_rent_amount - unit_advance
        unit_commission = (
            unit_rent_amount * commission_percentage / Decimal("100")
        ).quantize(Decimal("0.01"))
        unit_net = unit_rent_amount - unit_commission

        vendor_terms = VehicleDetailService._get_current_terms(listing)
        vendor_terms_snapshot = BookingCheckoutService._build_vendor_terms_snapshot(
            vendor_terms
        )

        # ── Platform T&C: fetch current LegalDocument, record acceptance ──
        platform_tc_doc = LegalDocumentRepository.get_current(
            LegalDocument.DocType.PLATFORM_TC
        )
        platform_tc_snapshot = BookingCheckoutService._build_platform_tc_snapshot(
            platform_tc_doc
        )
        if platform_tc_doc is not None:
            CustomerTCAcceptance.objects.get_or_create(
                user=customer,
                legal_document=platform_tc_doc,
                defaults={"ip_address": ip_address},
            )

        # ── Cancellation policy snapshot, frozen at booking time ──
        current_cancellation_policy = CancellationPolicyRepository.get_current()
        cancellation_snapshot = BookingCheckoutService._build_cancellation_snapshot(
            current_cancellation_policy
        )

        group_id = uuid.uuid4()
        bookings = []
        for _ in range(quantity):
            booking = Booking.objects.create(
                booking_group_id=group_id,
                booking_reference=_generate_unique_booking_reference(),
                customer=customer,
                listing=listing,
                pickup_location=listing.pickup_location,
                pickup_date=pickup_dt.date(),
                pickup_time=pickup_dt.time(),
                dropoff_date=dropoff_dt.date(),
                dropoff_time=dropoff_dt.time(),
                vehicle_count=1,
                pricing_package=pkg,
                price_snapshot={
                    "unit_rent_amount": str(unit_rent_amount),
                    "multiplier": str(multiplier),
                    "package_id": pkg.pk,
                },
                commission_percentage=commission_percentage,
                listing_amount=unit_rent_amount,
                commission_amount=unit_commission,
                discount_amount_on_commission=Decimal("0"),
                net_commission_amount=unit_commission,
                net_amount=unit_net,
                security_deposit_amount=listing.security_deposit_amount,
                payment_mode=effective_mode,
                advance_amount=unit_advance,
                remaining_amount=unit_remaining,
                platform_tc_document=platform_tc_doc,
                platform_tc_snapshot=platform_tc_snapshot,
                vendor_terms_version=vendor_terms,
                vendor_terms_snapshot=vendor_terms_snapshot,
                tc_accepted_at=timezone.now(),
                cancellation_policy_snapshot=cancellation_snapshot,
                status=Booking.Status.PENDING_PAYMENT,
                expires_at=timezone.now()
                + timedelta(
                    minutes=PlatformConfigService.get_int(
                        "PENDING_BOOKING_EXPIRY_MINUTES", default=15
                    )
                ),
            )
            bookings.append(booking)

        total_advance = unit_advance * quantity
        order_id = _generate_order_id()

        payment = Payment.objects.create(
            booking=bookings[0],
            payment_type=(
                Payment.PaymentType.PARTIAL
                if effective_mode == "PARTIAL"
                else Payment.PaymentType.FULL
            ),
            amount=total_advance,
            gateway="CASHFREE",
            gateway_order_id=order_id,
            status=Payment.Status.INITIATED,
        )

        try:
            cf_result = CashfreeClient.create_order(
                order_id=order_id,
                amount=total_advance,
                customer_id=f"cust_{customer.pk}",
                customer_name=f"{getattr(customer, 'first_name', '')} {getattr(customer, 'last_name', '')}".strip()
                or "Customer",
                customer_email=getattr(customer, "email", "") or "noemail@tripzido.com",
                customer_phone=getattr(customer, "phone_number", "") or "9999999999",
                return_url=return_url,
            )
        except Exception as exc:
            payment.status = Payment.Status.FAILED
            payment.failure_reason = str(exc)
            payment.failed_at = timezone.now()
            payment.save()
            for b in bookings:
                b.status = Booking.Status.PAYMENT_FAILED
                b.save()
            return None, "Unable to initiate payment. Please try again."

        payment.status = Payment.Status.PENDING
        payment.save()

        return {
            "order_id": order_id,
            "payment_session_id": cf_result["payment_session_id"],
            "amount": float(total_advance),
        }, None

    @staticmethod
    @transaction.atomic
    def confirm_payment_success(order_id: str, gateway_payload: dict) -> bool:
        payment = (
            Payment.objects.select_for_update()
            .filter(gateway_order_id=order_id)
            .first()
        )
        if payment is None:
            return False

        if payment.status == Payment.Status.SUCCESS:
            return True

        group_bookings = Booking.objects.select_for_update().filter(
            booking_group_id=payment.booking.booking_group_id
        )

        # If the group already expired (or was cancelled) before this
        # late-arriving confirmation showed up, do NOT silently revive it —
        # the held unit(s) may have already been released and resold.
        # Flag for manual reconciliation (payment captured, but booking no
        # longer valid) instead of pretending everything's fine.
        non_reconfirmable = group_bookings.exclude(
            status=Booking.Status.PENDING_PAYMENT
        )
        if non_reconfirmable.exists():
            payment.status = Payment.Status.SUCCESS
            payment.completed_at = timezone.now()
            payment.gateway_response = gateway_payload
            payment.webhook_received_at = timezone.now()
            payment.is_reconciled = False  # ← explicitly flag for ops review
            payment.failure_reason = (
                "Payment succeeded after booking group left PENDING_PAYMENT "
                f"(status: {non_reconfirmable.first().status}) — needs manual refund/resolution."
            )
            payment.save()
            return True

        payment.status = Payment.Status.SUCCESS
        payment.completed_at = timezone.now()
        payment.gateway_payment_id = (
            gateway_payload.get("data", {}).get("payment", {}).get("cf_payment_id", "")
        )
        payment.gateway_response = gateway_payload
        payment.webhook_received_at = timezone.now()
        payment.is_reconciled = True
        payment.save()

        for booking in group_bookings:
            booking.status = Booking.Status.CONFIRMED
            booking.save()

        return True

    @staticmethod
    @transaction.atomic
    def mark_payment_failed(order_id: str, reason: str) -> bool:
        payment = (
            Payment.objects.select_for_update()
            .filter(gateway_order_id=order_id)
            .first()
        )
        if payment is None:
            return False
        if payment.status in (Payment.Status.SUCCESS, Payment.Status.FAILED):
            return True

        payment.status = Payment.Status.FAILED
        payment.failed_at = timezone.now()
        payment.failure_reason = reason
        payment.webhook_received_at = timezone.now()
        payment.is_reconciled = True
        payment.save()

        Booking.objects.filter(
            booking_group_id=payment.booking.booking_group_id
        ).update(status=Booking.Status.PAYMENT_FAILED)

        return True

    @staticmethod
    def get_status(order_id: str) -> dict | None:
        payment = Payment.objects.filter(gateway_order_id=order_id).first()
        if payment is None:
            return None
        bookings = Booking.objects.filter(
            booking_group_id=payment.booking.booking_group_id
        )
        return {
            "status": payment.status,
            # Added: the frontend confirmation page needs this to build
            # /booking-confirmed?group=<uuid> — a single booking_reference
            # can't represent a bulk booking (multiple Booking rows share
            # one group id but each have their own reference).
            "booking_group_id": str(payment.booking.booking_group_id),
            "booking_references": [b.booking_reference for b in bookings],
        }


class BookingQueryService:

    # Maps the frontend tab name to the Booking.Status values it covers.
    # "cancelled" is intentionally broader than just CANCELLED — from the
    # customer's point of view, payment-failed and expired-unpaid bookings
    # are all "didn't happen" outcomes that belong in the same bucket.
    TAB_STATUS_MAP: dict[str, list[str]] = {
        "pending": [Booking.Status.PENDING_PAYMENT],
        "confirmed": [Booking.Status.CONFIRMED],
        "ongoing": [Booking.Status.ONGOING],
        "completed": [Booking.Status.COMPLETED],
        "cancelled": [
            Booking.Status.CANCELLED,
            Booking.Status.PAYMENT_FAILED,
            Booking.Status.EXPIRED,
        ],
    }

    @staticmethod
    def statuses_for_tab(tab: str) -> list[str] | None:
        """Returns the status list for a tab name, or None if unrecognised."""
        return BookingQueryService.TAB_STATUS_MAP.get(tab.lower())

    @staticmethod
    def get_customer_bookings(customer, tab: str):
        """
        Returns (queryset, None) on success, or (None, error_message) if
        `tab` isn't one of the recognised tab names.
        """
        statuses = BookingQueryService.statuses_for_tab(tab)
        if statuses is None:
            valid = ", ".join(BookingQueryService.TAB_STATUS_MAP.keys())
            return None, f"Invalid status filter. Must be one of: {valid}"

        return BookingRepository.get_bookings_for_customer(customer, statuses), None

    @staticmethod
    def get_booking_detail(booking_id: int, customer):
        """Returns the Booking instance, or None if not found / not owned by customer."""
        return BookingRepository.get_booking_by_id_for_customer(booking_id, customer)


class CancellationService:

    # Only a CONFIRMED booking can be cancelled through this flow.
    # PENDING_PAYMENT bookings carry no captured advance — nothing to
    # refund — and already auto-expire via Booking.expires_at, so the
    # customer can just let one lapse instead of explicitly cancelling.
    # ONGOING/COMPLETED/CANCELLED/PAYMENT_FAILED/EXPIRED are all terminal
    # or already-in-progress states where "cancel" doesn't apply.
    CANCELLABLE_STATUSES = [Booking.Status.CONFIRMED]

    @staticmethod
    def can_cancel(booking) -> tuple[bool, str | None]:
        if booking.status not in CancellationService.CANCELLABLE_STATUSES:
            return False, (
                f"Bookings in '{booking.get_status_display()}' status cannot be "
                "cancelled here."
            )
        return True, None

    @staticmethod
    def _hours_until_pickup(booking) -> Decimal:
        from datetime import datetime

        pickup_dt = datetime.combine(booking.pickup_date, booking.pickup_time)
        if timezone.is_aware(timezone.now()):
            pickup_dt = timezone.make_aware(pickup_dt)

        delta = pickup_dt - timezone.now()
        hours = Decimal(delta.total_seconds()) / Decimal(3600)
        # A booking whose pickup has already passed (shouldn't normally
        # reach here since it'd usually be ONGOING by then, but a vendor
        # who never marked handover could leave it CONFIRMED) is treated
        # as 0 hours out — the least generous tier — rather than a
        # negative number that wouldn't match any tier range.
        return max(hours, Decimal("0")).quantize(Decimal("0.01"))

    @staticmethod
    def _match_tier(policy, payment_mode: str, hours_before_pickup: Decimal):
        """
        Same range-matching as before, now scoped to the tiers belonging
        to `payment_mode`. FULL and PARTIAL schedules are independent —
        a booking never matches a tier from the other schedule.
        """
        for tier in policy.tiers.all():
            if tier.payment_mode != payment_mode:
                continue
            lower = Decimal(tier.min_hours_before_pickup)
            upper = (
                Decimal(tier.max_hours_before_pickup)
                if tier.max_hours_before_pickup is not None
                else None
            )
            if hours_before_pickup >= lower and (
                upper is None or hours_before_pickup < upper
            ):
                return tier
        return None

    @staticmethod
    def _tier_payment_mode(booking) -> str:
        """
        Maps Booking.PaymentMode -> CancellationTier.PaymentMode.
        PARTIAL bookings use the partial schedule (100% forfeiture per
        current policy). FULL and PAY_AT_PICKUP both use the full-payment
        schedule — PAY_AT_PICKUP shouldn't normally reach cancellation
        with money collected, but if it does, FULL is the safer default.
        """
        if booking.payment_mode == Booking.PaymentMode.PARTIAL:
            return CancellationTier.PaymentMode.PARTIAL
        return CancellationTier.PaymentMode.FULL

    @staticmethod
    def _match_tier_from_snapshot(
        tiers: list[dict], payment_mode: str, hours_before_pickup: Decimal
    ):
        """
        Same range-matching as _match_tier, but against the frozen
        dict-shaped tiers stored in Booking.cancellation_policy_snapshot
        instead of live CancellationTier rows.
        """
        for tier in tiers:
            if tier["payment_mode"] != payment_mode:
                continue
            lower = Decimal(tier["min_hours_before_pickup"])
            upper = (
                Decimal(tier["max_hours_before_pickup"])
                if tier["max_hours_before_pickup"] is not None
                else None
            )
            if hours_before_pickup >= lower and (
                upper is None or hours_before_pickup < upper
            ):
                return Decimal(tier["refund_percentage"])
        return None

    @staticmethod
    def _resolve_refund_percentage(booking) -> tuple[Decimal, dict]:
        """
        Prefers the policy frozen on the booking at checkout time
        (cancellation_policy_snapshot) so that a later policy edit never
        changes what a customer is entitled to for a booking made under
        the old terms. Falls back to a live lookup only for bookings
        created before this snapshot existed (empty/missing snapshot).
        """
        hours_before_pickup = CancellationService._hours_until_pickup(booking)
        tier_payment_mode = CancellationService._tier_payment_mode(booking)

        snapshot = booking.cancellation_policy_snapshot or {}
        snapshot_tiers = snapshot.get("tiers")

        if snapshot_tiers:
            refund_percentage = CancellationService._match_tier_from_snapshot(
                snapshot_tiers, tier_payment_mode, hours_before_pickup
            )
            meta = {
                "policy_version": snapshot.get("policy_version"),
                "hours_before_pickup": hours_before_pickup,
            }
            return refund_percentage or Decimal("0"), meta

        # Legacy fallback: booking predates the snapshot feature.
        policy = CancellationPolicyRepository.get_current()
        tier = (
            CancellationService._match_tier(
                policy, tier_payment_mode, hours_before_pickup
            )
            if policy
            else None
        )
        refund_percentage = tier.refund_percentage if tier else Decimal("0")

        meta = {
            "policy_version": policy.version if policy else None,
            "hours_before_pickup": hours_before_pickup,
        }
        return refund_percentage, meta

    @staticmethod
    @transaction.atomic
    def cancel_booking(
        booking,
        cancelled_by_user,
        reason_code: str,
        reason_text: str = "",
    ) -> tuple[BookingCancellation | None, str | None]:
        """
        Cancels a CONFIRMED booking: computes the refund entitlement
        from administrations.CancellationPolicy's current tiers, records
        a BookingCancellation, and flips the booking to CANCELLED.

        Does NOT call out to Cashfree to actually issue the refund —
        refundable_amount/forfeited_amount are computed and recorded
        only. Triggering the real gateway refund is a separate,
        not-yet-built step.

        Returns (BookingCancellation, None) on success, or
        (None, error_message) if cancellation isn't allowed right now.
        """
        booking = Booking.objects.select_for_update().get(pk=booking.pk)

        allowed, error = CancellationService.can_cancel(booking)
        if not allowed:
            return None, error

        if reason_code not in BookingCancellation.CUSTOMER_REASON_CODES:
            return None, "Invalid cancellation reason."

        refund_percentage, meta = CancellationService._resolve_refund_percentage(
            booking
        )

        paid_amount = booking.advance_amount  # what's actually been collected
        refundable_amount = (paid_amount * refund_percentage / Decimal("100")).quantize(
            Decimal("0.01")
        )
        forfeited_amount = paid_amount - refundable_amount

        cancellation = BookingCancellationRepository.create_cancellation_record(
            booking=booking,
            cancelled_by=cancelled_by_user,
            cancelled_by_role=Booking.CancelledBy.CUSTOMER,
            reason_code=reason_code,
            reason_text=reason_text,
            policy_version=meta["policy_version"],
            hours_before_pickup_at_cancellation=meta["hours_before_pickup"],
            refund_percentage=refund_percentage,
            refundable_amount=refundable_amount,
            forfeited_amount=forfeited_amount,
        )

        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.cancelled_by_role = Booking.CancelledBy.CUSTOMER
        booking.save(update_fields=["status", "cancelled_at", "cancelled_by_role"])

        return cancellation, None

    @staticmethod
    def preview_cancellation(booking) -> tuple[dict | None, str | None]:
        allowed, error = CancellationService.can_cancel(booking)
        if not allowed:
            return None, error

        refund_percentage, meta = CancellationService._resolve_refund_percentage(
            booking
        )

        paid_amount = booking.advance_amount
        refundable_amount = (paid_amount * refund_percentage / Decimal("100")).quantize(
            Decimal("0.01")
        )
        forfeited_amount = paid_amount - refundable_amount

        policy_info = CancellationPolicyService.get_current_policy()

        return {
            "payment_mode": booking.payment_mode,
            "hours_before_pickup": float(meta["hours_before_pickup"]),
            "refund_percentage": float(refund_percentage),
            "paid_amount": float(paid_amount),
            "refundable_amount": float(refundable_amount),
            "forfeited_amount": float(forfeited_amount),
            "full_payment_rules": (
                policy_info["full_payment_rules"] if policy_info else []
            ),
            "partial_payment_rules": (
                policy_info["partial_payment_rules"] if policy_info else []
            ),
            "policy_note": policy_info["note"] if policy_info else "",
        }, None
