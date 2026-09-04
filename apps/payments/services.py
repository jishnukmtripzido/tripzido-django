from django.db.models import Q
from django.utils import timezone
from apps.payments.models import Payment, RefundRecord, VendorPayout
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification
from apps.payments.repositories import (
    AdminEligibleBookingRepository,
    AdminRefundRepository,
    AdminVendorPayoutRepository,
    VendorPayoutRepository,
)
from apps.logs.services import ActivityLogService


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
        payout, error = AdminVendorPayoutRepository.update_status(
            payout_id, target_status, admin_user, utr_number, note
        )
        if payout is None:
            return None, error

        # Only PAID/FAILED are notification-worthy — a payout sitting
        # in PENDING is an internal admin batching step the vendor
        # doesn't need a push about yet; they find out once it's
        # actually resolved one way or the other.
        if target_status == VendorPayout.Status.PAID:
            NotificationService.notify_vendor_and_team(
                vendor=payout.vendor,
                portal=Notification.Portal.VENDOR,
                notification_type=Notification.NotificationType.PAYOUT_PAID,
                title="Payout completed",
                message=f"₹{payout.total_amount} has been transferred (UTR: {payout.utr_number}).",
                link=f"/ledger/detail?id={payout.id}",
            )
        elif target_status == VendorPayout.Status.FAILED:
            NotificationService.notify_vendor_and_team(
                vendor=payout.vendor,
                portal=Notification.Portal.VENDOR,
                notification_type=Notification.NotificationType.PAYOUT_FAILED,
                title="Payout failed",
                message=f"Your payout of ₹{payout.total_amount} could not be completed. Contact support for details.",
                link=f"/ledger/detail?id={payout.id}",
            )

        actor_role = "SUPER_ADMIN" if admin_user.has_role("SUPER_ADMIN") else "SUPPORT"
        ActivityLogService.log(
            actor=admin_user,
            actor_role=actor_role,
            action=f"PAYOUT_{target_status}",
            target_model="VendorPayout",
            target_id=payout.id,
            target_label=f"₹{payout.total_amount} to {payout.vendor.business_name}",
            description=note,
            metadata={"utr_number": utr_number} if utr_number else {},
        )
        return payout, None


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


class AdminRefundService:

    @staticmethod
    def get_all(status_filter=None, search=None):
        return AdminRefundRepository.get_all(status_filter, search)

    @staticmethod
    def update_status(
        refund_id: int,
        target_status: str,
        admin_user,
        reference_number: str = "",
        note: str = "",
    ):
        refund = AdminRefundRepository.get_by_id(refund_id)
        if refund is None:
            return None, "Refund not found"

        if target_status == RefundRecord.Status.PROCESSED:
            if not reference_number.strip():
                return (
                    None,
                    "A reference number is required to mark this refund as processed.",
                )
            refund.reference_number = reference_number
            refund.processed_at = timezone.now()
            refund.processed_by = admin_user
        elif target_status == RefundRecord.Status.PENDING:
            # Reset — e.g. correcting a mistaken mark-as-processed.
            refund.processed_at = None
            refund.processed_by = None

        if note:
            refund.note = note

        refund.status = target_status
        refund.save()

        actor_role = "SUPER_ADMIN" if admin_user.has_role("SUPER_ADMIN") else "SUPPORT"
        ActivityLogService.log(
            actor=admin_user,
            actor_role=actor_role,
            action=f"REFUND_{target_status}",
            target_model="RefundRecord",
            target_id=refund.id,
            target_label=f"₹{refund.amount} refund",
            description=note,
        )

        return refund, None
