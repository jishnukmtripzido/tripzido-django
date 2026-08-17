from django.db.models import Q

from apps.payments.models import Payment
from apps.payments.repositories import (
    AdminEligibleBookingRepository,
    AdminVendorPayoutRepository,
    VendorPayoutRepository,
)


class VendorPayoutService:

    @staticmethod
    def get_for_vendor(vendor_id: int):
        return VendorPayoutRepository.get_for_vendor(vendor_id)

    @staticmethod
    def get_detail_for_vendor(payout_id: int, vendor_id: int):
        return VendorPayoutRepository.get_detail_for_vendor(payout_id, vendor_id)


class AdminEligibleBookingService:
    @staticmethod
    def get_all(vendor_id=None, search=None):
        return AdminEligibleBookingRepository.get_all(vendor_id, search)


class AdminVendorPayoutService:
    @staticmethod
    def get_all(vendor_id=None, status_filter=None):
        return AdminVendorPayoutRepository.get_all(vendor_id, status_filter)

    @staticmethod
    def get_detail(payout_id: int):
        return AdminVendorPayoutRepository.get_by_id(payout_id)

    @staticmethod
    def create(vendor_id, booking_ids, period_start=None, period_end=None, note=""):
        return AdminVendorPayoutRepository.create(
            vendor_id, booking_ids, period_start, period_end, note
        )

    @staticmethod
    def update_status(payout_id, target_status, admin_user, utr_number="", note=""):
        return AdminVendorPayoutRepository.update_status(
            payout_id, target_status, admin_user, utr_number, note
        )


class AdminPaymentService:
    @staticmethod
    def get_all(status_filter=None, search=None, is_reconciled=None):
        qs = Payment.objects.select_related("booking__listing__vendor").order_by(
            "-initiated_at"
        )
        if status_filter:
            qs = qs.filter(status=status_filter)
        if is_reconciled is not None:
            qs = qs.filter(is_reconciled=is_reconciled)
        if search:
            qs = qs.filter(
                Q(gateway_order_id__icontains=search)
                | Q(gateway_payment_id__icontains=search)
                | Q(booking__booking_reference__icontains=search)
            )
        return qs

    @staticmethod
    def toggle_reconciled(payment_id: int):
        payment = Payment.objects.filter(id=payment_id).first()
        if payment is None:
            return None
        payment.is_reconciled = not payment.is_reconciled
        payment.save(update_fields=["is_reconciled"])
        return payment
