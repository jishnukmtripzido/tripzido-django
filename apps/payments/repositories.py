from django.db import transaction
from django.db.models import Prefetch, Q
from apps.bookings.models import Booking
from apps.payments.models import RefundRecord, VendorPayout, VendorPayoutItem
from apps.vendors.models import BankAccount


class VendorPayoutRepository:

    @staticmethod
    def get_for_vendor(vendor_id: int):
        """
        Every payout ever made to this vendor, newest first — powers
        the Ledger list screen. Not filtered by status; the frontend
        badge (Pending/Paid/Failed) reflects VendorPayout.status
        directly, same as the mock "SUCCESS" badge it's replacing.
        """
        return VendorPayout.objects.filter(vendor_id=vendor_id).order_by("-created_at")

    @staticmethod
    def get_detail_for_vendor(payout_id: int, vendor_id: int):
        """
        Ownership enforced via vendor_id in the filter itself — same
        IDOR-safe pattern as every other vendor-scoped repository
        method in this codebase. Prefetches items with their linked
        booking's vehicle info, since the detail page needs to show
        which bookings this payout actually covers.
        """
        return (
            VendorPayout.objects.filter(id=payout_id, vendor_id=vendor_id)
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=VendorPayoutItem.objects.select_related(
                        "booking__listing__vehicle_type"
                    ).order_by("-created_at"),
                )
            )
            .first()
        )


class AdminEligibleBookingRepository:

    @staticmethod
    def get_all(vendor_id=None, search=None):
        qs = (
            Booking.objects.filter(
                payment_mode=Booking.PaymentMode.FULL,
                status=Booking.Status.COMPLETED,
                payout_item__isnull=True,
            )
            .select_related("listing__vendor", "listing__vehicle_type__brand")
            .order_by("-dropoff_date")
        )
        if vendor_id:
            qs = qs.filter(listing__vendor_id=vendor_id)
        if search:
            qs = qs.filter(
                Q(booking_reference__icontains=search)
                | Q(listing__vendor__business_name__icontains=search)
            )
        return qs


class AdminVendorPayoutRepository:

    @staticmethod
    def get_all(vendor_id=None, status_filter=None):
        qs = VendorPayout.objects.select_related("vendor").order_by("-created_at")
        if vendor_id:
            qs = qs.filter(vendor_id=vendor_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @staticmethod
    def get_by_id(payout_id: int):
        return (
            VendorPayout.objects.filter(id=payout_id)
            .select_related("vendor", "paid_by")
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=VendorPayoutItem.objects.select_related(
                        "booking__listing__vehicle_type__brand"
                    ),
                )
            )
            .first()
        )

    @staticmethod
    @transaction.atomic
    def create(
        vendor_id: int,
        booking_ids: list[int],
        period_start=None,
        period_end=None,
        note="",
    ):
        bank_snapshot = {}
        active_account = BankAccount.objects.filter(
            vendor_id=vendor_id, is_active_acc=True
        ).first()
        if active_account:
            bank_snapshot = {
                "account_holder_name": active_account.account_holder_name,
                "account_number": active_account.account_number,
                "ifsc_code": active_account.ifsc_code,
                "bank_name": active_account.bank_name,
            }

        payout = VendorPayout.objects.create(
            vendor_id=vendor_id,
            status=VendorPayout.Status.PENDING,
            period_start=period_start,
            period_end=period_end,
            bank_account_snapshot=bank_snapshot,
            note=note,
        )

        # Re-filters against the eligibility rule rather than trusting
        # booking_ids blindly — any id that isn't actually this
        # vendor's, or isn't FULL/COMPLETED, or is already in another
        # payout, is silently dropped here rather than erroring. The
        # created payout's item count reflects only what was truly
        # eligible; a caller passing stale ids just gets fewer items
        # than requested, not a 400.
        eligible_bookings = Booking.objects.filter(
            id__in=booking_ids,
            listing__vendor_id=vendor_id,
            payment_mode=Booking.PaymentMode.FULL,
            status=Booking.Status.COMPLETED,
            payout_item__isnull=True,
        )
        # bulk_create bypasses each instance's save(), so amount must
        # be set explicitly here — VendorPayoutItem.save()'s own
        # auto-fill-from-booking.net_amount fallback never runs.
        items = [
            VendorPayoutItem(payout=payout, booking=b, amount=b.net_amount)
            for b in eligible_bookings
        ]
        VendorPayoutItem.objects.bulk_create(items)
        payout.recompute_total()
        return payout

    @staticmethod
    @transaction.atomic
    def update_status(
        payout_id: int,
        target_status: str,
        admin_user,
        utr_number: str = "",
        note: str = "",
    ):
        from django.utils import timezone

        payout = VendorPayout.objects.select_for_update().filter(id=payout_id).first()
        if payout is None:
            return None, "Payout not found"

        if target_status == VendorPayout.Status.PAID:
            if not utr_number.strip():
                return None, "UTR number is required to mark a payout as paid."
            payout.utr_number = utr_number
            if not payout.paid_by:
                payout.paid_by = admin_user
            if not payout.paid_at:
                payout.paid_at = timezone.now()
        if note:
            payout.note = note

        payout.status = target_status
        payout.save()
        return payout, None


class AdminRefundRepository:

    @staticmethod
    def get_all(status_filter=None, search=None):
        qs = RefundRecord.objects.select_related(
            "cancellation__booking__customer",
            "cancellation__booking__listing__vendor",
            "processed_by",
        ).order_by("-created_at")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(
                Q(cancellation__booking__booking_reference__icontains=search)
                | Q(cancellation__booking__customer__phone_number__icontains=search)
                | Q(
                    cancellation__booking__listing__vendor__business_name__icontains=search
                )
            )
        return qs

    @staticmethod
    def get_by_id(refund_id: int):
        return (
            RefundRecord.objects.select_related(
                "cancellation__booking__customer",
                "cancellation__booking__listing__vendor",
                "processed_by",
            )
            .filter(id=refund_id)
            .first()
        )
