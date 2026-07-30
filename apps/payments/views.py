from rest_framework.generics import GenericAPIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from apps.payments.serializers import (
    VendorPayoutListSerializer,
    VendorPayoutDetailSerializer,
)
from apps.payments.services import VendorPayoutService
from apps.core.responses import success_response, error_response
from apps.core.pagination import CustomPagination


class VendorPayoutsView(GenericAPIView):
    """
    GET /api/payments/vendor/payouts/

    Lists every payout ever made to the authenticated vendor, newest
    first. Same vendor_profile ownership check as every other
    vendor-scoped endpoint in this codebase — a token with no linked
    Vendor profile gets nothing.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VendorPayoutListSerializer
    pagination_class = CustomPagination

    def get(self, request):
        vendor = getattr(request.user, "vendor_profile", None)
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        payouts = VendorPayoutService.get_for_vendor(vendor.id)
        page = self.paginate_queryset(payouts)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Payouts retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VendorPayoutDetailView(GenericAPIView):
    """
    GET /api/payments/vendor/payouts/<int:payout_id>/

    Full detail for a single payout, including every booking it
    covers — the "which bookings does this ₹6,320.36 actually pay for"
    breakdown.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VendorPayoutDetailSerializer

    def get(self, request, payout_id: int):
        vendor = getattr(request.user, "vendor_profile", None)
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        payout = VendorPayoutService.get_detail_for_vendor(payout_id, vendor.id)
        if payout is None:
            return error_response(
                message="Payout not found", status=status.HTTP_404_NOT_FOUND
            )

        serializer = VendorPayoutDetailSerializer(payout)
        return success_response(
            data=serializer.data,
            message="Payout details retrieved successfully",
            status=status.HTTP_200_OK,
        )
