from rest_framework.generics import GenericAPIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from apps.payments.serializers import (
    AdminRefundSerializer,
    AdminRefundStatusUpdateSerializer,
    VendorPayoutListSerializer,
    VendorPayoutDetailSerializer,
    AdminEligibleBookingSerializer,
    AdminVendorPayoutListSerializer,
    AdminVendorPayoutCreateSerializer,
    AdminVendorPayoutDetailSerializer,
    AdminVendorPayoutStatusUpdateSerializer,
    AdminPaymentSerializer,
)
from apps.payments.services import (
    AdminRefundService,
    VendorPayoutService,
    AdminEligibleBookingService,
    AdminVendorPayoutService,
    AdminPaymentService,
)
from apps.payments.repositories import AdminRefundRepository
from apps.core.responses import success_response, error_response
from apps.core.pagination import CustomPagination
from apps.core.permissions import IsStaffRole


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


class AdminEligibleBookingListView(GenericAPIView):
    """
    GET /api/payments/admin/eligible-bookings/?vendor_id=&search=&page=
    Every FULL-payment, COMPLETED booking not yet attached to any
    payout — same eligibility rule EligibleVendorBooking (Django Admin)
    already used, exposed here for the create-payout flow.
    """

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminEligibleBookingSerializer
    pagination_class = CustomPagination

    def get(self, request):
        vendor_id = request.query_params.get("vendor_id")
        search = request.query_params.get("search")
        queryset = AdminEligibleBookingService.get_all(
            int(vendor_id) if vendor_id else None, search
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Eligible bookings retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminVendorPayoutListCreateView(GenericAPIView):
    """GET/POST /api/payments/admin/payouts/?vendor_id=&status=&page="""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorPayoutListSerializer
    pagination_class = CustomPagination

    def get(self, request):
        vendor_id = request.query_params.get("vendor_id")
        status_filter = request.query_params.get("status")
        queryset = AdminVendorPayoutService.get_all(
            int(vendor_id) if vendor_id else None, status_filter
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Payouts retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminVendorPayoutCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        payout = AdminVendorPayoutService.create(
            data["vendor_id"],
            data["booking_ids"],
            data.get("period_start"),
            data.get("period_end"),
            data.get("note", ""),
        )
        output = AdminVendorPayoutDetailSerializer(
            AdminVendorPayoutService.get_detail(payout.id)
        )
        return success_response(
            data=output.data,
            message="Payout created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminVendorPayoutDetailView(GenericAPIView):
    """GET /api/payments/admin/payouts/<int:payout_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorPayoutDetailSerializer

    def get(self, request, payout_id: int):
        payout = AdminVendorPayoutService.get_detail(payout_id)
        if payout is None:
            return error_response(
                message="Payout not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(payout)
        return success_response(
            data=serializer.data,
            message="Payout retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminVendorPayoutStatusUpdateView(GenericAPIView):
    """PATCH /api/payments/admin/payouts/<int:payout_id>/status/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorPayoutStatusUpdateSerializer

    def patch(self, request, payout_id: int):
        serializer = AdminVendorPayoutStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        payout, error = AdminVendorPayoutService.update_status(
            payout_id,
            data["status"],
            request.user,
            data.get("utr_number", ""),
            data.get("note", ""),
        )
        if payout is None:
            code = (
                status.HTTP_404_NOT_FOUND
                if error == "Payout not found"
                else status.HTTP_400_BAD_REQUEST
            )
            return error_response(message=error, status=code)
        output = AdminVendorPayoutDetailSerializer(
            AdminVendorPayoutService.get_detail(payout_id)
        )
        return success_response(
            data=output.data,
            message="Payout status updated successfully",
            status=status.HTTP_200_OK,
        )


class AdminPaymentListView(GenericAPIView):
    """GET /api/payments/admin/payments/?status=&search=&is_reconciled=&page="""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminPaymentSerializer
    pagination_class = CustomPagination

    def get(self, request):
        status_filter = request.query_params.get("status")
        search = request.query_params.get("search")
        raw_reconciled = request.query_params.get("is_reconciled")
        is_reconciled = (
            raw_reconciled.lower() == "true" if raw_reconciled is not None else None
        )
        queryset = AdminPaymentService.get_all(status_filter, search, is_reconciled)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Payments retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminPaymentToggleReconciledView(GenericAPIView):
    """PATCH /api/payments/admin/payments/<int:payment_id>/toggle-reconciled/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminPaymentSerializer

    def patch(self, request, payment_id: int):
        payment = AdminPaymentService.toggle_reconciled(payment_id)
        if payment is None:
            return error_response(
                message="Payment not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(payment)
        return success_response(
            data=serializer.data,
            message="Payment reconciliation status updated",
            status=status.HTTP_200_OK,
        )


class AdminRefundListView(GenericAPIView):
    """GET /api/payments/admin/refunds/?status=&search=&page="""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminRefundSerializer
    pagination_class = CustomPagination

    def get(self, request):
        status_filter = request.query_params.get("status")
        search = request.query_params.get("search")
        queryset = AdminRefundService.get_all(status_filter, search)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Refunds retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminRefundDetailView(GenericAPIView):
    """GET /api/payments/admin/refunds/<int:refund_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminRefundSerializer

    def get(self, request, refund_id: int):
        refund = AdminRefundRepository.get_by_id(refund_id)
        if refund is None:
            return error_response(
                message="Refund not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(refund)
        return success_response(
            data=serializer.data,
            message="Refund retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminRefundStatusUpdateView(GenericAPIView):
    """PATCH /api/payments/admin/refunds/<int:refund_id>/status/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminRefundStatusUpdateSerializer

    def patch(self, request, refund_id: int):
        serializer = AdminRefundStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        refund, error = AdminRefundService.update_status(
            refund_id,
            data["status"],
            request.user,
            data.get("reference_number", ""),
            data.get("note", ""),
        )
        if refund is None:
            code = (
                status.HTTP_404_NOT_FOUND
                if error == "Refund not found"
                else status.HTTP_400_BAD_REQUEST
            )
            return error_response(message=error, status=code)
        output = AdminRefundSerializer(refund)
        return success_response(
            data=output.data,
            message="Refund status updated successfully",
            status=status.HTTP_200_OK,
        )
