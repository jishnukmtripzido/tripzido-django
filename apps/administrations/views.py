from django.db import transaction
from django.utils import timezone

from rest_framework.generics import GenericAPIView
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.administrations.services import (
    CancellationPolicyService,
    OfferService,
    PopularRentalService,
    AnnouncementBannerService,
    LegalDocumentService,
    AdminDashboardService,
)
from apps.administrations.serializers import (
    AdminDashboardSerializer,
    CancellationPolicySerializer,
    OfferSerializer,
    PopularRentalSerializer,
    PopularRentalQuerySerializer,
    AnnouncementBannerSerializer,
    AnnouncementBannerQuerySerializer,
    LegalDocumentSerializer,
    AdminTaxRateSerializer,
    AdminPlatformConfigSerializer,
    AdminLegalDocumentSerializer,
    AdminLegalDocumentCreateSerializer,
    AdminOfferSerializer,
    AdminPopularRentalSerializer,
    AdminAnnouncementBannerSerializer,
    AdminCancellationPolicyListSerializer,
    AdminCancellationPolicyCreateSerializer,
    AdminCancellationPolicyDetailSerializer,
)
from apps.administrations.models import (
    CancellationPolicy,
    CancellationTier,
    LegalDocument,
    TaxRate,
    PlatformConfig,
    Offer,
    PopularRental,
    AnnouncementBanner,
)
from apps.core.pagination import CustomPagination
from apps.core.responses import success_response, error_response
from apps.users.permissions import IsStaffRole


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


class AdminTaxRateListCreateView(GenericAPIView):
    """
    GET  /api/administrations/admin/tax-rates/?context=&page=
    POST /api/administrations/admin/tax-rates/

    No PATCH/DELETE — TaxRate is an immutable version history by
    design (the model's own save() already auto-bumps version and
    unsets the old "current" row for that context). "Editing" a rate
    means creating a new version via POST, never mutating an old one.
    """

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminTaxRateSerializer
    pagination_class = CustomPagination

    def get(self, request):
        items = TaxRate.objects.all()
        context = request.query_params.get("context")
        if context:
            items = items.filter(context=context)
        page = self.paginate_queryset(items)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Tax rates retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminTaxRateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminTaxRateSerializer(instance).data,
            message="Tax rate version created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminPlatformConfigListCreateView(GenericAPIView):
    """GET/POST /api/administrations/admin/platform-config/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminPlatformConfigSerializer

    def get(self, request):
        items = PlatformConfig.objects.all()
        serializer = self.get_serializer(items, many=True)
        return success_response(
            data=serializer.data,
            message="Platform config retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminPlatformConfigSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminPlatformConfigSerializer(instance).data,
            message="Config created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminPlatformConfigDetailView(GenericAPIView):
    """PATCH/DELETE /api/administrations/admin/platform-config/<int:config_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminPlatformConfigSerializer

    def patch(self, request, config_id: int):
        instance = PlatformConfig.objects.filter(id=config_id).first()
        if instance is None:
            return error_response(
                message="Config not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = AdminPlatformConfigSerializer(
            instance, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminPlatformConfigSerializer(instance).data,
            message="Config updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, config_id: int):
        instance = PlatformConfig.objects.filter(id=config_id).first()
        if instance is None:
            return error_response(
                message="Config not found", status=status.HTTP_404_NOT_FOUND
            )
        instance.delete()
        return success_response(
            data=None,
            message="Config deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminOfferListCreateView(GenericAPIView):
    """GET/POST /api/administrations/admin/offers/?is_active="""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminOfferSerializer

    def get(self, request):
        items = Offer.objects.all()
        is_active = request.query_params.get("is_active")
        if is_active is not None:
            items = items.filter(is_active=is_active.lower() == "true")
        serializer = self.get_serializer(items, many=True)
        return success_response(
            data=serializer.data,
            message="Offers retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminOfferSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminOfferSerializer(instance).data,
            message="Offer created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminOfferDetailView(GenericAPIView):
    """PATCH/DELETE /api/administrations/admin/offers/<int:offer_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminOfferSerializer

    def patch(self, request, offer_id: int):
        instance = Offer.objects.filter(id=offer_id).first()
        if instance is None:
            return error_response(
                message="Offer not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = AdminOfferSerializer(instance, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminOfferSerializer(instance).data,
            message="Offer updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, offer_id: int):
        instance = Offer.objects.filter(id=offer_id).first()
        if instance is None:
            return error_response(
                message="Offer not found", status=status.HTTP_404_NOT_FOUND
            )
        instance.delete()
        return success_response(
            data=None,
            message="Offer deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminPopularRentalListCreateView(GenericAPIView):
    """GET/POST /api/administrations/admin/popular-rentals/?city_id="""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminPopularRentalSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        items = PopularRental.objects.select_related(
            "city", "vehicle_type__brand", "pickup_location"
        ).all()
        city_id = request.query_params.get("city_id")
        if city_id:
            items = items.filter(city_id=city_id)
        serializer = self.get_serializer(items, many=True)
        return success_response(
            data=serializer.data,
            message="Popular rentals retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminPopularRentalSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminPopularRentalSerializer(instance).data,
            message="Popular rental created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminPopularRentalDetailView(GenericAPIView):
    """PATCH/DELETE /api/administrations/admin/popular-rentals/<int:rental_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminPopularRentalSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def patch(self, request, rental_id: int):
        instance = PopularRental.objects.filter(id=rental_id).first()
        if instance is None:
            return error_response(
                message="Popular rental not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = AdminPopularRentalSerializer(
            instance, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminPopularRentalSerializer(instance).data,
            message="Popular rental updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, rental_id: int):
        instance = PopularRental.objects.filter(id=rental_id).first()
        if instance is None:
            return error_response(
                message="Popular rental not found", status=status.HTTP_404_NOT_FOUND
            )
        instance.delete()
        return success_response(
            data=None,
            message="Popular rental deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminAnnouncementBannerListCreateView(GenericAPIView):
    """GET/POST /api/administrations/admin/banners/?page="""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminAnnouncementBannerSerializer

    def get(self, request):
        items = AnnouncementBanner.objects.all()
        page_filter = request.query_params.get("page")
        if page_filter:
            items = items.filter(page=page_filter)
        serializer = self.get_serializer(items, many=True)
        return success_response(
            data=serializer.data,
            message="Banners retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminAnnouncementBannerSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminAnnouncementBannerSerializer(instance).data,
            message="Banner created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminAnnouncementBannerDetailView(GenericAPIView):
    """PATCH/DELETE /api/administrations/admin/banners/<int:banner_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminAnnouncementBannerSerializer

    def patch(self, request, banner_id: int):
        instance = AnnouncementBanner.objects.filter(id=banner_id).first()
        if instance is None:
            return error_response(
                message="Banner not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = AdminAnnouncementBannerSerializer(
            instance, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminAnnouncementBannerSerializer(instance).data,
            message="Banner updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, banner_id: int):
        instance = AnnouncementBanner.objects.filter(id=banner_id).first()
        if instance is None:
            return error_response(
                message="Banner not found", status=status.HTTP_404_NOT_FOUND
            )
        instance.delete()
        return success_response(
            data=None,
            message="Banner deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminCancellationPolicyListCreateView(GenericAPIView):
    """
    GET  /api/administrations/admin/cancellation-policies/?page=
    POST /api/administrations/admin/cancellation-policies/

    No PATCH — immutable version history, same reasoning as TaxRate/
    LegalDocument. "Editing" the policy means submitting a complete new
    set of tiers as a new version; the old version and its tiers stay
    untouched (BookingCancellation snapshots which tier applied at
    cancellation time via policy_version, so history must never shift).
    """

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminCancellationPolicyListSerializer
    pagination_class = CustomPagination

    def get(self, request):
        items = CancellationPolicy.objects.all()
        page = self.paginate_queryset(items)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Cancellation policies retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminCancellationPolicyCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        with transaction.atomic():
            policy = CancellationPolicy.objects.create(
                name=data["name"],
                refund_note=data["refund_note"],
                is_current=data["is_current"],
            )
            tiers = [
                CancellationTier(
                    policy=policy,
                    payment_mode=t["payment_mode"],
                    min_hours_before_pickup=t["min_hours_before_pickup"],
                    max_hours_before_pickup=t.get("max_hours_before_pickup"),
                    refund_percentage=t["refund_percentage"],
                    label=t.get("label", ""),
                    description=t.get("description", ""),
                )
                for t in data["tiers"]
            ]
            CancellationTier.objects.bulk_create(tiers)

        output = AdminCancellationPolicyDetailSerializer(policy)
        return success_response(
            data=output.data,
            message="Cancellation policy version created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminCancellationPolicyDetailView(GenericAPIView):
    """GET /api/administrations/admin/cancellation-policies/<int:policy_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminCancellationPolicyDetailSerializer

    def get(self, request, policy_id: int):
        policy = (
            CancellationPolicy.objects.prefetch_related("tiers")
            .filter(id=policy_id)
            .first()
        )
        if policy is None:
            return error_response(
                message="Cancellation policy not found",
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(policy)
        return success_response(
            data=serializer.data,
            message="Cancellation policy retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminLegalDocumentListCreateView(GenericAPIView):
    """
    GET  /api/administrations/admin/legal-documents/?doc_type=&page=
    POST /api/administrations/admin/legal-documents/

    No PATCH — same immutable-version-history reasoning. Marking
    is_current=True on create is treated as the "publish" action:
    published_at/published_by stamp automatically at that moment,
    rather than requiring a separate publish step the model itself
    doesn't otherwise provide.
    """

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminLegalDocumentSerializer
    pagination_class = CustomPagination

    def get(self, request):
        items = LegalDocument.objects.select_related("published_by").all()
        doc_type = request.query_params.get("doc_type")
        if doc_type:
            items = items.filter(doc_type=doc_type)
        page = self.paginate_queryset(items)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Legal documents retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminLegalDocumentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        doc = LegalDocument(
            doc_type=data["doc_type"],
            content=data["content"],
            is_current=data["is_current"],
        )
        if data["is_current"]:
            doc.published_at = timezone.now()
            doc.published_by = request.user
        doc.save()

        output = AdminLegalDocumentSerializer(doc)
        return success_response(
            data=output.data,
            message="Legal document version created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminDashboardView(GenericAPIView):
    """GET /api/administrations/admin/dashboard/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminDashboardSerializer

    def get(self, request):
        data = AdminDashboardService.get_dashboard()
        serializer = self.get_serializer(data)
        return success_response(
            data=serializer.data,
            message="Dashboard retrieved successfully",
            status=status.HTTP_200_OK,
        )
