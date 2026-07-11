from rest_framework.generics import GenericAPIView
from rest_framework import status
from rest_framework.permissions import AllowAny

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.administrations.services import (
    CancellationPolicyService,
    OfferService,
    PopularRentalService,
    AnnouncementBannerService,
    LegalDocumentService,
)
from apps.administrations.serializers import (
    CancellationPolicySerializer,
    OfferSerializer,
    PopularRentalSerializer,
    PopularRentalQuerySerializer,
    AnnouncementBannerSerializer,
    AnnouncementBannerQuerySerializer,
    LegalDocumentSerializer,
)
from apps.core.responses import success_response, error_response
from apps.administrations.models import LegalDocument


class CancellationPolicyView(GenericAPIView):
    permission_classes = [AllowAny]

    def get(self, request, **kwargs):
        # kwargs absorbs any path params (e.g. vehicleId) — policy is platform-wide
        data = CancellationPolicyService.get_current_policy()

        if data is None:
            return error_response(
                message="No cancellation policy found",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CancellationPolicySerializer(data)
        return success_response(
            data=serializer.data,
            message="Cancellation policy retrieved successfully",
            status=status.HTTP_200_OK,
        )


class OfferListView(GenericAPIView):
    """
    GET /api/administrations/offers/

    Returns all active offer cards ordered by sort_order.
    The first item has is_featured=true — that is the yellow card.
    """

    permission_classes = [AllowAny]
    serializer_class = OfferSerializer

    @extend_schema(
        responses=OfferSerializer(many=True),
    )
    def get(self, request):
        try:
            offers = OfferService.get_offers()
            serializer = OfferSerializer(offers, many=True)
            return success_response(
                data=serializer.data,
                message="Offers retrieved successfully",
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return error_response(
                message="Failed to retrieve offers",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PopularRentalListView(GenericAPIView):
    """
    GET /api/administrations/popular-rentals/?city_id=<int>

    Returns active popular rental cards for the given city ordered by
    sort_order. Powers the "Popular rentals in <City>" homepage carousel.
    """

    permission_classes = [AllowAny]
    serializer_class = PopularRentalSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="city_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="ID of the city whose popular rentals to fetch.",
            ),
        ],
        responses=PopularRentalSerializer(many=True),
    )
    def get(self, request):
        query_serializer = PopularRentalQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            return error_response(
                message="Invalid parameters",
                errors=query_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        city_id = query_serializer.validated_data["city_id"]

        try:
            rentals = PopularRentalService.get_popular_rentals(city_id)
            serializer = PopularRentalSerializer(
                rentals, many=True, context={"request": request}
            )
            return success_response(
                data=serializer.data,
                message="Popular rentals retrieved successfully",
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return error_response(
                message="Failed to retrieve popular rentals",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AnnouncementBannerView(GenericAPIView):
    """
    GET /api/administrations/announcement-banner/?page=search_result

    Returns the current active announcement banner for the given page,
    or null if none is set.
    """

    permission_classes = [AllowAny]
    serializer_class = AnnouncementBannerSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Page identifier: search_result | vehicle_detail | home",
            ),
        ],
        responses=AnnouncementBannerSerializer,
    )
    def get(self, request):
        query_serializer = AnnouncementBannerQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            return error_response(
                message="Invalid parameters",
                errors=query_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        page = query_serializer.validated_data["page"]

        try:
            banner = AnnouncementBannerService.get_current_banner(page)
            if banner is None:
                return success_response(
                    data=None,
                    message="No active banner for this page",
                    status=status.HTTP_200_OK,
                )
            serializer = AnnouncementBannerSerializer(banner)
            return success_response(
                data=serializer.data,
                message="Banner retrieved successfully",
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return error_response(
                message="Failed to retrieve banner",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LegalDocumentView(GenericAPIView):
    """
    GET /api/administrations/legal-document/?doc_type=PLATFORM_TC

    Returns the current version of a platform legal document. Used by
    the checkout terms modal, and reusable for footer Terms/Privacy links.
    """

    permission_classes = [AllowAny]
    serializer_class = LegalDocumentSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="doc_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="PLATFORM_TC | PRIVACY_POLICY",
            ),
        ],
        responses=LegalDocumentSerializer,
    )
    def get(self, request):
        doc_type = request.query_params.get("doc_type")
        valid_types = [c[0] for c in LegalDocument.DocType.choices]
        if doc_type not in valid_types:
            return error_response(
                message="Invalid or missing doc_type",
                errors={"doc_type": f"Must be one of {valid_types}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        doc = LegalDocumentService.get_current(doc_type)
        if doc is None:
            return error_response(
                message="No current document found for this type",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = LegalDocumentSerializer(doc)
        return success_response(
            data=serializer.data,
            message="Legal document retrieved successfully",
            status=status.HTTP_200_OK,
        )
