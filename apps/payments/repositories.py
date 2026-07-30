from django.db.models import Prefetch
from apps.payments.models import VendorPayout, VendorPayoutItem


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
