# apps/vendors/views.py
from rest_framework.generics import GenericAPIView
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.vendors.serializers import (
    AdminBankAccountReviewSerializer,
    AdminBankAccountSerializer,
    AdminDocumentReviewSerializer,
    AdminSubscriptionPlanSerializer,
    AdminVendorCommissionSerializer,
    AdminVendorDetailSerializer,
    AdminVendorDocumentSerializer,
    AdminVendorListSerializer,
    AdminVendorRegistrationSerializer,
    AdminVendorStatusUpdateSerializer,
    AdminVendorSubscriptionAssignSerializer,
    AdminVendorSubscriptionSerializer,
    AdminVendorTeamMemberCreateSerializer,
    AdminVendorTeamMemberSerializer,
    VendorDashboardAttentionSerializer,
    VendorDashboardFleetSerializer,
    VendorDashboardRecentBookingsSerializer,
    VendorDashboardStatsSerializer,
    VendorDashboardStatusSerializer,
    VendorTermsSerializer,
    VendorTermsUpdateSerializer,
    VendorDashboardSerializer,
)
from apps.vendors.services import (
    AdminBankAccountService,
    AdminSubscriptionPlanService,
    AdminVendorCommissionService,
    AdminVendorDocumentService,
    AdminVendorRegistrationService,
    AdminVendorService,
    AdminVendorSubscriptionService,
    AdminVendorTeamService,
    VendorTermsService,
    VendorDashboardService,
)
from apps.core.responses import success_response, error_response
from apps.core.pagination import CustomPagination
from apps.users.permissions import IsStaffRole


class VendorTermsView(GenericAPIView):
    """
    GET /api/vendors/<vendor_id>/terms/
    Public/customer-facing read of a vendor's current terms — shown on
    the vehicle detail page. Not vendor-scoped to the caller; kept
    entirely separate from VendorTermsManageView below.
    """

    permission_classes = [AllowAny]
    serializer_class = VendorTermsSerializer

    @extend_schema(responses=VendorTermsSerializer)
    def get(self, request, vendor_id: int):
        terms = VendorTermsService.get_current_terms(vendor_id)
        if terms is None:
            return error_response(
                message="No current terms found for this vendor",
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = VendorTermsSerializer(terms)
        return success_response(
            data=serializer.data,
            message="Vendor terms retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VendorTermsManageView(GenericAPIView):
    """
    GET  /api/vendors/me/terms/  — the authenticated vendor's own current terms
    POST /api/vendors/me/terms/  — save changes as a new version

    Always request.user's own vendor_profile — no vendor_id in the
    URL, so this can never be pointed at another vendor's terms.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VendorTermsSerializer

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        terms = VendorTermsService.get_current_terms(vendor.id)
        if terms is None:
            # Not an error — a vendor who hasn't set terms yet just
            # gets an empty form on the frontend.
            return success_response(
                data=None,
                message="No terms configured yet",
                status=status.HTTP_200_OK,
            )
        serializer = VendorTermsSerializer(terms)
        return success_response(
            data=serializer.data,
            message="Terms retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        input_serializer = VendorTermsUpdateSerializer(data=request.data)
        if not input_serializer.is_valid():
            return error_response(
                message="Invalid terms data",
                errors=input_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        terms = VendorTermsService.save_new_version(
            vendor.id, input_serializer.validated_data
        )
        output_serializer = VendorTermsSerializer(terms)
        return success_response(
            data=output_serializer.data,
            message="Terms saved — new version created",
            status=status.HTTP_201_CREATED,
        )


class VendorDashboardView(GenericAPIView):
    """GET /api/vendors/me/dashboard/"""

    permission_classes = [IsAuthenticated]
    serializer_class = VendorDashboardSerializer

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        data = VendorDashboardService.get_dashboard(vendor)
        serializer = VendorDashboardSerializer(data, context={"request": request})
        return success_response(
            data=serializer.data,
            message="Dashboard retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminVendorListView(GenericAPIView):
    """GET /api/vendors/admin/vendors/?status=&search=&page="""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorListSerializer
    pagination_class = CustomPagination

    def get(self, request):
        status_filter = request.query_params.get("status")
        search = request.query_params.get("search")
        queryset = AdminVendorService.get_all(status_filter, search)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Vendors retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminVendorDetailView(GenericAPIView):
    """GET /api/vendors/admin/vendors/<int:vendor_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorDetailSerializer

    def get(self, request, vendor_id: int):
        vendor = AdminVendorService.get_detail(vendor_id)
        if vendor is None:
            return error_response(
                message="Vendor not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(vendor)
        return success_response(
            data=serializer.data,
            message="Vendor retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminVendorStatusUpdateView(GenericAPIView):
    """PATCH /api/vendors/admin/vendors/<int:vendor_id>/status/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorStatusUpdateSerializer

    def patch(self, request, vendor_id: int):
        serializer = AdminVendorStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        vendor, error = AdminVendorService.update_status(
            vendor_id,
            serializer.validated_data["status"],
            request.user,
            serializer.validated_data["reason"],
        )
        if vendor is None:
            code = (
                status.HTTP_404_NOT_FOUND
                if error == "Vendor not found"
                else status.HTTP_400_BAD_REQUEST
            )
            return error_response(message=error, status=code)
        output = AdminVendorDetailSerializer(vendor)
        return success_response(
            data=output.data,
            message="Vendor status updated successfully",
            status=status.HTTP_200_OK,
        )


class AdminVendorDocumentsView(GenericAPIView):
    """GET /api/vendors/admin/vendors/<int:vendor_id>/documents/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorDocumentSerializer

    def get(self, request, vendor_id: int):
        docs = AdminVendorDocumentService.get_for_vendor(vendor_id)
        serializer = self.get_serializer(docs, many=True)
        return success_response(
            data=serializer.data,
            message="Documents retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminDocumentReviewView(GenericAPIView):
    """PATCH /api/vendors/admin/documents/<int:doc_id>/review/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminDocumentReviewSerializer

    def patch(self, request, doc_id: int):
        serializer = AdminDocumentReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        doc, error = AdminVendorDocumentService.review(
            doc_id,
            request.user,
            serializer.validated_data["status"],
            serializer.validated_data["rejection_reason"],
        )
        if doc is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)
        output = AdminVendorDocumentSerializer(doc)
        return success_response(
            data=output.data,
            message="Document reviewed successfully",
            status=status.HTTP_200_OK,
        )


class AdminVendorBankAccountsView(GenericAPIView):
    """GET /api/vendors/admin/vendors/<int:vendor_id>/bank-accounts/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminBankAccountSerializer

    def get(self, request, vendor_id: int):
        accounts = AdminBankAccountService.get_for_vendor(vendor_id)
        serializer = self.get_serializer(accounts, many=True)
        return success_response(
            data=serializer.data,
            message="Bank accounts retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminBankAccountReviewView(GenericAPIView):
    """PATCH /api/vendors/admin/bank-accounts/<int:account_id>/review/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminBankAccountReviewSerializer

    def patch(self, request, account_id: int):
        serializer = AdminBankAccountReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        account, error = AdminBankAccountService.review(
            account_id,
            request.user,
            serializer.validated_data["status"],
            serializer.validated_data["rejection_reason"],
        )
        if account is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)
        output = AdminBankAccountSerializer(account)
        return success_response(
            data=output.data,
            message="Bank account reviewed successfully",
            status=status.HTTP_200_OK,
        )


class AdminVendorCommissionListCreateView(GenericAPIView):
    """GET/POST /api/vendors/admin/commissions/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorCommissionSerializer

    def get(self, request):
        items = AdminVendorCommissionService.get_all()
        serializer = self.get_serializer(items, many=True)
        return success_response(
            data=serializer.data,
            message="Commissions retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminVendorCommissionSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = AdminVendorCommissionService.create(serializer.validated_data)
        output = AdminVendorCommissionSerializer(instance)
        return success_response(
            data=output.data,
            message="Commission created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminVendorCommissionDetailView(GenericAPIView):
    """PATCH/DELETE /api/vendors/admin/commissions/<int:commission_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorCommissionSerializer

    def patch(self, request, commission_id: int):
        serializer = AdminVendorCommissionSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = AdminVendorCommissionService.update(
            commission_id, serializer.validated_data
        )
        if instance is None:
            return error_response(
                message="Commission not found", status=status.HTTP_404_NOT_FOUND
            )
        output = AdminVendorCommissionSerializer(instance)
        return success_response(
            data=output.data,
            message="Commission updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, commission_id: int):
        deleted, error = AdminVendorCommissionService.delete(commission_id)
        if not deleted:
            if error == "not_found":
                return error_response(
                    message="Commission not found", status=status.HTTP_404_NOT_FOUND
                )
            return error_response(
                message="This commission structure is used by one or more subscription plans and can't be deleted.",
                status=status.HTTP_409_CONFLICT,
            )
        return success_response(
            data=None,
            message="Commission deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminVendorSubscriptionsView(GenericAPIView):
    """GET /api/vendors/admin/vendors/<int:vendor_id>/subscriptions/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorSubscriptionSerializer

    def get(self, request, vendor_id: int):
        items = AdminVendorSubscriptionService.get_for_vendor(vendor_id)
        serializer = self.get_serializer(items, many=True)
        return success_response(
            data=serializer.data,
            message="Subscription history retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminVendorSubscriptionAssignView(GenericAPIView):
    """POST /api/vendors/admin/vendors/<int:vendor_id>/subscriptions/assign/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorSubscriptionAssignSerializer

    def post(self, request, vendor_id: int):
        serializer = AdminVendorSubscriptionAssignSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        sub, error = AdminVendorSubscriptionService.assign(
            vendor_id, serializer.validated_data["plan_id"], request.user
        )
        if sub is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)
        output = AdminVendorSubscriptionSerializer(sub)
        return success_response(
            data=output.data,
            message="Subscription plan assigned successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminSubscriptionPlanListCreateView(GenericAPIView):
    """GET/POST /api/vendors/admin/subscription-plans/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminSubscriptionPlanSerializer

    def get(self, request):
        items = AdminSubscriptionPlanService.get_all()
        serializer = self.get_serializer(items, many=True)
        return success_response(
            data=serializer.data,
            message="Plans retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminSubscriptionPlanSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = AdminSubscriptionPlanService.create(serializer.validated_data)
        output = AdminSubscriptionPlanSerializer(instance)
        return success_response(
            data=output.data,
            message="Plan created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminSubscriptionPlanDetailView(GenericAPIView):
    """GET/PATCH/DELETE /api/vendors/admin/subscription-plans/<int:plan_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminSubscriptionPlanSerializer

    def get(self, request, plan_id: int):
        instance = AdminSubscriptionPlanService.get_detail(plan_id)
        if instance is None:
            return error_response(
                message="Plan not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(instance)
        return success_response(
            data=serializer.data,
            message="Plan retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def patch(self, request, plan_id: int):
        serializer = AdminSubscriptionPlanSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = AdminSubscriptionPlanService.update(
            plan_id, serializer.validated_data
        )
        if instance is None:
            return error_response(
                message="Plan not found", status=status.HTTP_404_NOT_FOUND
            )
        output = AdminSubscriptionPlanSerializer(instance)
        return success_response(
            data=output.data,
            message="Plan updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, plan_id: int):
        deleted, error = AdminSubscriptionPlanService.delete(plan_id)
        if not deleted:
            if error == "not_found":
                return error_response(
                    message="Plan not found", status=status.HTTP_404_NOT_FOUND
                )
            return error_response(
                message="This plan has vendors subscribed to it (currently or historically) and can't be deleted.",
                status=status.HTTP_409_CONFLICT,
            )
        return success_response(
            data=None,
            message="Plan deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminVendorRegistrationView(GenericAPIView):
    """POST /api/vendors/admin/register/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorRegistrationSerializer

    def post(self, request):
        serializer = AdminVendorRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        vendor, error = AdminVendorRegistrationService.register(
            serializer.validated_data, request.user
        )
        if vendor is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)

        output = AdminVendorDetailSerializer(vendor)
        return success_response(
            data=output.data,
            message="Vendor registered successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminVendorTeamView(GenericAPIView):
    """
    GET  /api/vendors/admin/vendors/<int:vendor_id>/team/
    POST /api/vendors/admin/vendors/<int:vendor_id>/team/
    """

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorTeamMemberSerializer

    def get(self, request, vendor_id: int):
        members = AdminVendorTeamService.get_team(vendor_id)
        data = [
            {
                "id": m.id,
                "user_id": m.user_id,
                "full_name": m.user.get_full_name(),
                "phone_number": m.user.phone_number,
                "email": m.user.email,
                "added_at": m.created_at,
                "added_by_name": m.added_by.get_full_name() if m.added_by else None,
                "is_active": m.is_active,
            }
            for m in members
        ]
        serializer = self.get_serializer(data, many=True)
        return success_response(
            data=serializer.data,
            message="Team members retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request, vendor_id: int):
        serializer = AdminVendorTeamMemberCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        member, error = AdminVendorTeamService.add_team_member(
            vendor_id, serializer.validated_data, request.user
        )
        if member is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data={
                "id": member.id,
                "user_id": member.user_id,
                "full_name": member.user.get_full_name(),
                "phone_number": member.user.phone_number,
                "email": member.user.email,
                "added_at": member.created_at,
                "added_by_name": request.user.get_full_name(),
                "is_active": True,
            },
            message="Team member added successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminVendorTeamMemberDetailView(GenericAPIView):
    """DELETE /api/vendors/admin/team/<int:member_id>/ — permanent, irreversible."""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorTeamMemberSerializer

    def delete(self, request, member_id: int):
        deleted = AdminVendorTeamService.hard_delete_team_member(member_id)
        if not deleted:
            return error_response(
                message="Team member not found", status=status.HTTP_404_NOT_FOUND
            )
        return success_response(
            data=None,
            message="Team member permanently deleted",
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminVendorTeamMemberDeactivateView(GenericAPIView):
    """PATCH /api/vendors/admin/team/<int:member_id>/deactivate/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorTeamMemberSerializer

    def patch(self, request, member_id: int):
        ok = AdminVendorTeamService.deactivate_team_member(
            member_id, deactivated_by=request.user
        )
        if not ok:
            return error_response(
                message="Team member not found", status=status.HTTP_404_NOT_FOUND
            )
        return success_response(
            data=None, message="Team member deactivated", status=status.HTTP_200_OK
        )


class AdminVendorTeamMemberRestoreView(GenericAPIView):
    """PATCH /api/vendors/admin/team/<int:member_id>/restore/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVendorTeamMemberSerializer

    def patch(self, request, member_id: int):
        ok = AdminVendorTeamService.restore_team_member(member_id)
        if not ok:
            return error_response(
                message="Team member not found", status=status.HTTP_404_NOT_FOUND
            )
        return success_response(
            data=None, message="Team member reactivated", status=status.HTTP_200_OK
        )


class VendorDashboardStatusView(GenericAPIView):
    """GET /api/vendors/me/dashboard/status/ — vendor status + balance only."""

    permission_classes = [IsAuthenticated]
    serializer_class = VendorDashboardStatusSerializer

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        data = VendorDashboardService.get_status_and_balance(vendor)
        serializer = self.get_serializer(data)
        return success_response(
            data=serializer.data,
            message="Dashboard status retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VendorDashboardAttentionView(GenericAPIView):
    """GET /api/vendors/me/dashboard/attention/ — bookings needing action."""

    permission_classes = [IsAuthenticated]
    serializer_class = VendorDashboardAttentionSerializer

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        data = VendorDashboardService.get_needs_attention_section(vendor)
        serializer = self.get_serializer(data, context={"request": request})
        return success_response(
            data=serializer.data,
            message="Needs-attention bookings retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VendorDashboardStatsView(GenericAPIView):
    """GET /api/vendors/me/dashboard/stats/ — revenue/orders trend + weekly chart."""

    permission_classes = [IsAuthenticated]
    serializer_class = VendorDashboardStatsSerializer

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        data = VendorDashboardService.get_stats(vendor)
        serializer = self.get_serializer(data)
        return success_response(
            data=serializer.data,
            message="Dashboard stats retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VendorDashboardFleetView(GenericAPIView):
    """GET /api/vendors/me/dashboard/fleet/ — fleet counts snapshot."""

    permission_classes = [IsAuthenticated]
    serializer_class = VendorDashboardFleetSerializer

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        data = VendorDashboardService.get_fleet_section(vendor)
        serializer = self.get_serializer(data)
        return success_response(
            data=serializer.data,
            message="Fleet snapshot retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VendorDashboardRecentBookingsView(GenericAPIView):
    """GET /api/vendors/me/dashboard/recent-bookings/"""

    permission_classes = [IsAuthenticated]
    serializer_class = VendorDashboardRecentBookingsSerializer

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        data = VendorDashboardService.get_recent_bookings_section(vendor)
        serializer = self.get_serializer(data, context={"request": request})
        return success_response(
            data=serializer.data,
            message="Recent bookings retrieved successfully",
            status=status.HTTP_200_OK,
        )
