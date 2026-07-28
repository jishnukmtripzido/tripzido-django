# apps/vendors/views.py
from rest_framework.generics import GenericAPIView
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.vendors.serializers import VendorTermsSerializer, VendorTermsUpdateSerializer
from apps.vendors.services import VendorTermsService
from apps.core.responses import success_response, error_response


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
        vendor = getattr(request.user, "vendor_profile", None)
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
        vendor = getattr(request.user, "vendor_profile", None)
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
