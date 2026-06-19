import uuid
import secrets
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from apps.bookings.models import Booking, Payment
from apps.bookings.cashfree_client import CashfreeClient
from apps.vehicles.repositories import VehicleDetailRepository
from apps.vehicles.services import AvailabilityService, VehicleDetailService
from django.conf import settings


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
