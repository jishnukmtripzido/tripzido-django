from django.shortcuts import render

# Create your views here.
# apps/vendors/views.py (add)
from rest_framework.generics import GenericAPIView
from rest_framework import status
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema

from apps.vendors.serializers import VendorTermsSerializer
from apps.vendors.services import VendorTermsService
from apps.core.responses import success_response, error_response


class VendorTermsView(GenericAPIView):
    """
    GET /api/vendors/<vendor_id>/terms/
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
