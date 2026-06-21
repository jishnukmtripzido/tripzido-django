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
from apps.administrations.services import CancellationPolicyService


def _generate_booking_reference() -> str:
    return "TRZ" + secrets.token_hex(4).upper()


def _generate_order_id() -> str:
    # Cashfree order ids are alphanumeric + _ / - ; keep it short and safe.
    return "bk_" + uuid.uuid4().hex[:20]


class BookingCheckoutService:

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
    ) -> tuple[dict | None, str | None]:
        """
        Validates availability/pricing, creates N Booking rows (one per
        vehicle) + one Payment row, then creates the matching Cashfree
        order. Returns (result, None) on success or (None, error) if
        validation fails before any Cashfree call is made.
        """
        listing = VehicleDetailRepository.get_listing_by_id(listing_id)
        if listing is None:
            return None, "Vehicle listing not found"

        if quantity < 1:
            return None, "Quantity must be at least 1"
        if quantity > listing.available_count:
            return None, "Requested quantity exceeds availability"

        is_available, message = AvailabilityService.is_available(
            listing_id, pickup_dt, dropoff_dt
        )
        if not is_available:
            return None, message

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

        terms = VehicleDetailService._get_current_terms(listing)

        group_id = uuid.uuid4()
        bookings = []
        for _ in range(quantity):
            booking = Booking.objects.create(
                booking_group_id=group_id,
                booking_reference=_generate_booking_reference(),
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
                platform_tc_version=settings.PLATFORM_TC_VERSION,
                vendor_terms_version=terms,
                tc_accepted_at=timezone.now(),
                cancellation_policy_snapshot={},
                status=Booking.Status.PENDING_PAYMENT,
                expires_at=timezone.now() + timedelta(minutes=15),
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
        """
        Idempotent: returns True if this call (or a prior one) already
        confirmed this order, False if the order_id wasn't found at all.
        Used by both the webhook handler and the polling fallback.
        """
        payment = (
            Payment.objects.select_for_update()
            .filter(gateway_order_id=order_id)
            .first()
        )
        if payment is None:
            return False

        if payment.status == Payment.Status.SUCCESS:
            return True  # already processed — duplicate webhook delivery

        payment.status = Payment.Status.SUCCESS
        payment.completed_at = timezone.now()
        payment.gateway_payment_id = (
            gateway_payload.get("data", {}).get("payment", {}).get("cf_payment_id", "")
        )
        payment.gateway_response = gateway_payload
        payment.webhook_received_at = timezone.now()
        payment.is_reconciled = True
        payment.save()

        group_bookings = Booking.objects.select_for_update().filter(
            booking_group_id=payment.booking.booking_group_id
        )
        listing = None
        for booking in group_bookings:
            booking.status = Booking.Status.CONFIRMED
            booking.save()
            listing = booking.listing

        if listing is not None:
            # NOTE: not re-checking availability here on purpose — if a
            # race condition let this slip through, that's a genuine
            # overbooking edge case needing manual ops/refund handling,
            # not something to silently auto-cancel after money has
            # already moved. Flagging as a known gap, not solving it here.
            listing.available_count = max(
                0, listing.available_count - group_bookings.count()
            )
            listing.save()

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
    def _match_tier(policy, hours_before_pickup: Decimal):
        """
        Finds the administrations.CancellationTier whose
        [min_hours_before_pickup, max_hours_before_pickup) range
        contains hours_before_pickup. Tiers are expected to tile the
        timeline without gaps/overlaps (e.g. 0-24, 24-48, 48+) — that's
        an admin-configuration concern, not enforced here. Returns None
        if no tier matches (e.g. an incompletely configured policy).
        """
        for tier in policy.tiers.all():
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
    def _resolve_refund_percentage(booking) -> tuple[Decimal, dict]:
        """
        Shared by cancel_booking and preview_cancellation: looks up the
        current policy via administrations.CancellationPolicyRepository,
        matches a tier by hours-until-pickup, and returns
        (refund_percentage, meta) where meta carries the policy_version
        and hours figure needed for the BookingCancellation snapshot /
        preview response.

        Fails safe to 0% refund if no policy is configured at all, or
        if no tier matches the exact timing — never silently grants a
        full refund nobody approved.
        """
        policy = CancellationPolicyRepository.get_current()
        hours_before_pickup = CancellationService._hours_until_pickup(booking)

        tier = (
            CancellationService._match_tier(policy, hours_before_pickup)
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
        a BookingCancellation, flips the booking to CANCELLED, and
        restores one unit to the listing's available_count (mirroring
        how confirm_payment_success decremented it on confirmation).

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

        listing = booking.listing
        listing.available_count = listing.available_count + booking.vehicle_count
        listing.save(update_fields=["available_count"])

        return cancellation, None

    @staticmethod
    def preview_cancellation(booking) -> tuple[dict | None, str | None]:
        """
        Read-only version of the refund math in cancel_booking, used to
        show the customer "you'll get ₹X back" before they confirm.
        Does not create any records or change booking state.

        Also includes the full policy schedule (every tier's label /
        description / refund_percentage, via
        CancellationPolicyService.get_current_policy()) so the frontend
        can show the whole refund timeline, not just the customer's one
        matched outcome.
        """
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
            "hours_before_pickup": float(meta["hours_before_pickup"]),
            "refund_percentage": float(refund_percentage),
            "paid_amount": float(paid_amount),
            "refundable_amount": float(refundable_amount),
            "forfeited_amount": float(forfeited_amount),
            "policy_rules": policy_info["rules"] if policy_info else [],
            "policy_note": policy_info["note"] if policy_info else "",
        }, None
