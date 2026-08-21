# apps/vehicles/views.py

from django.db.models import ProtectedError
from rest_framework.generics import GenericAPIView
from rest_framework import status
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from apps.vehicles.serializers import (
    AdminBrandSerializer,
    AdminListingListSerializer,
    AdminListingDetailSerializer,
    AdminListingStatusUpdateSerializer,
    AdminPricingPackageTypeSerializer,
    BrandOptionSerializer,
    VehicleSearchQuerySerializer,
    VehicleSearchResultSerializer,
    VehicleReviewItemSerializer,
    VehicleDetailSerializer,
    CheckoutSummaryQuerySerializer,
    CheckoutSummarySerializer,
    LocationTimingSerializer,
    VendorFleetListingSerializer,
    VendorListingDetailSerializer,
    VendorListingCreateSerializer,
    VehicleTypeOptionSerializer,
    PackageTypeOptionSerializer,
    ScheduleTemplateSerializer,
    VendorListingImageDetailSerializer,
    VendorBlockedPeriodListSerializer,
    VendorBlockedPeriodCreateSerializer,
    VendorBlockedPeriodUpdateSerializer,
    ScheduleTemplateCreateSerializer,
    VendorListingStatusSerializer,
    VendorPickupPointSerializer,
    VendorListingUpdateSerializer,
    AdminVehicleTypeSerializer,
    AdminPackageCategorySerializer,
)
from apps.vehicles.models import Brand, PricingPackageType, VehicleType, PackageCategory
from django.db.models import Q
from apps.vehicles.services import (
    BrandService,
    VehicleSearchService,
    VehicleReviewService,
    VehicleReviewService,
    VehicleDetailService,
    LocationTimingService,
    VendorFleetService,
    VendorListingDetailService,
    VendorListingCreateService,
    VendorListingImageService,
    VehicleTypeService,
    ScheduleTemplateService,
    PackageTypeService,
    VendorListingUpdateService,
    VendorBlockedPeriodService,
    VendorPickupPointService,
    AdminListingService,
)
from apps.core.responses import success_response, error_response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.permissions import AllowAny, IsAuthenticated
from apps.users.permissions import IsStaffRole
from apps.core.pagination import CustomPagination
from django.db import IntegrityError
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView


class VehicleSearchView(GenericAPIView):
    serializer_class = VehicleSearchResultSerializer

    def get_permissions(self):
        """
        Determine the permissions required for the current request.
        Returns:
            list: A list containing the appropriate permission classes based on the HTTP method.
                  - If the request method is "GET", it returns [AllowAny()], allowing unrestricted access.
                  - For other methods, it returns [IsAuthenticated()], restricting access to authenticated users.
        """

        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return VehicleSearchService.search(
            city_id=self._validated_params["city_id"],
            pickup_datetime=self._validated_params["pickup_datetime"],
            dropoff_datetime=self._validated_params["dropoff_datetime"],
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="city_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="ID of the city to search vehicles in",
            ),
            OpenApiParameter(
                name="vehicle_type_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Restrict results to a single vehicle type (used when resolving a location change from the detail page)",
            ),
            OpenApiParameter(
                name="pickup_datetime",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Pickup datetime e.g. 2025-06-01T10:00:00",
            ),
            OpenApiParameter(
                name="dropoff_datetime",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Dropoff datetime e.g. 2025-06-02T10:00:00",
            ),
        ],
        responses=VehicleSearchResultSerializer(many=True),
    )
    def get(self, request):
        query_serializer = VehicleSearchQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            return error_response(
                message="Invalid search parameters",
                errors=query_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            vehicle_types = VehicleSearchService.search(
                city_id=query_serializer.validated_data["city_id"],
                pickup_datetime=query_serializer.validated_data["pickup_datetime"],
                dropoff_datetime=query_serializer.validated_data["dropoff_datetime"],
                vehicle_type_id=query_serializer.validated_data.get("vehicle_type_id"),
            )
            serializer = self.get_serializer(vehicle_types, many=True)
            return success_response(
                data=serializer.data,
                message="Vehicles retrieved successfully",
                status=status.HTTP_200_OK,
            )

        except ValidationError as e:
            return error_response(
                message="Search validation failed",
                errors=e.messages,
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return error_response(
                message="Failed to retrieve vehicles",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VehicleDetailView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = VehicleDetailSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="location_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Location ID",
            ),
            OpenApiParameter(
                name="location_name",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Location name",
            ),
            OpenApiParameter(
                name="city_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="City ID",
            ),
            OpenApiParameter(
                name="package_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Package ID",
            ),
            OpenApiParameter(
                name="pickup_datetime",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Pickup datetime (ISO 8601), e.g. 2026-06-17T10:00:00",
            ),
            OpenApiParameter(
                name="dropoff_datetime",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Dropoff datetime (ISO 8601), e.g. 2026-06-18T10:00:00",
            ),
        ],
        responses=VehicleDetailSerializer,
    )
    def get(self, request, listing_id: int):

        if not listing_id:
            return error_response(
                message="listing_id is required",
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = VehicleDetailService.get_vehicle_detail(listing_id, request=request)

        if data is None:
            return error_response(
                message="Vehicle listing not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = VehicleDetailSerializer(data)
        return success_response(
            data=serializer.data,
            message="Vehicle details retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VehicleReviewsView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = VehicleReviewItemSerializer
    pagination_class = CustomPagination

    def get(self, request, listing_id: int):
        try:
            data = VehicleReviewService.get_listing_reviews(listing_id)

            page = self.paginate_queryset(data["reviews_queryset"])
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)

            response_data = {
                "average_rating": data["average_rating"],
                **paginated_response.data,  # adds "pagination" and "results"
            }

            return success_response(
                data=response_data,
                message="Reviews retrieved successfully",
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return error_response(
                message="Failed to retrieve reviews",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CheckoutSummaryView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = CheckoutSummarySerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="listing_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
            OpenApiParameter(
                name="package_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
            OpenApiParameter(
                name="pickup_datetime",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
            OpenApiParameter(
                name="dropoff_datetime",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
        ],
        responses=CheckoutSummarySerializer,
    )
    def get(self, request):
        query_serializer = CheckoutSummaryQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            return error_response(
                message="Invalid checkout parameters",
                errors=query_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        data, error = VehicleDetailService.get_checkout_summary(
            listing_id=query_serializer.validated_data["listing_id"],
            package_id=query_serializer.validated_data["package_id"],
            pickup_dt=query_serializer.validated_data["pickup_datetime"],
            dropoff_dt=query_serializer.validated_data["dropoff_datetime"],
            request=request,
        )

        if data is None:
            return error_response(
                message=error or "Unable to build checkout summary",
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CheckoutSummarySerializer(data)
        return success_response(
            data=serializer.data,
            message="Checkout summary retrieved successfully",
            status=status.HTTP_200_OK,
        )


class LocationTimingView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = LocationTimingSerializer

    @extend_schema(responses=LocationTimingSerializer)
    def get(self, request, listing_id: int):
        try:
            data = LocationTimingService.get_location_timing(listing_id)
        except Exception as e:
            return error_response(
                message="Failed to retrieve location timing",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if data is None:
            # No schedule template assigned — frontend treats null as
            # "don't render this section".
            return success_response(
                data=None,
                message="No schedule configured for this listing",
                status=status.HTTP_200_OK,
            )

        serializer = LocationTimingSerializer(data)
        return success_response(
            data=serializer.data,
            message="Location timing retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VendorFleetListView(GenericAPIView):
    """
    GET /api/vehicles/vendor/fleet/

    Lists the authenticated vendor's own listings, every status
    included. Requires the caller's User to have a linked Vendor
    profile — this is a second, independent authorization layer on
    top of login-time role gating: even if a non-vendor token somehow
    reached this endpoint, there's no vendor_profile to scope data to,
    so nothing leaks.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VendorFleetListingSerializer
    pagination_class = CustomPagination

    @extend_schema(responses=VendorFleetListingSerializer(many=True))
    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            listings = VendorFleetService.get_fleet_for_vendor(vendor.id)
            page = self.paginate_queryset(listings)
            serializer = self.get_serializer(
                page, many=True, context={"request": request}
            )
            paginated_response = self.get_paginated_response(serializer.data)

            return success_response(
                data=paginated_response.data,  # {"pagination": ..., "results": ...} — same shape VehicleReviewsView already returns
                message="Fleet retrieved successfully",
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return error_response(
                message="Failed to retrieve fleet",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = VendorListingCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid listing data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            listing = VendorListingCreateService.create_listing(
                vendor, serializer.validated_data
            )
        except ValidationError as e:
            return error_response(
                message="Validation failed",
                errors=e.message_dict if hasattr(e, "message_dict") else str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            return error_response(
                message="A listing for this vehicle type at this location already exists.",
                status=status.HTTP_409_CONFLICT,
            )

        # Reuse the same detail-shape response the listing detail page
        # already fetches — one response shape for both "just created"
        # and "viewing later", so the frontend can redirect straight
        # into /fleet/listing?id=X after a successful create with zero
        # extra mapping logic.
        detail = VendorListingDetailService.get_detail(
            listing.id, vendor.id, request=request
        )
        output_serializer = VendorListingDetailSerializer(detail)
        return success_response(
            data=output_serializer.data,
            message="Listing created successfully",
            status=status.HTTP_201_CREATED,
        )


class VendorListingDetailView(GenericAPIView):
    """
    GET /api/vehicles/vendor/fleet/<int:listing_id>/

    Full detail for a single listing owned by the authenticated
    vendor. Ownership is enforced inside the repository query
    (vendor_id filter), not as a check after fetching — a listing
    belonging to a different vendor returns 404, never partial data.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VendorListingDetailSerializer

    @extend_schema(responses=VendorListingDetailSerializer)
    def get(self, request, listing_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        data = VendorListingDetailService.get_detail(
            listing_id, vendor.id, request=request
        )
        if data is None:
            return error_response(
                message="Listing not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = VendorListingDetailSerializer(data)
        return success_response(
            data=serializer.data,
            message="Listing details retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def patch(self, request, listing_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = VendorListingUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid listing data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            listing = VendorListingUpdateService.update_listing(
                listing_id, vendor, serializer.validated_data
            )
        except ValidationError as e:
            return error_response(
                message="Validation failed",
                errors=e.message_dict if hasattr(e, "message_dict") else str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            return error_response(
                message="A listing for this vehicle type at this location already exists.",
                status=status.HTTP_409_CONFLICT,
            )

        if listing is None:
            return error_response(
                message="Listing not found", status=status.HTTP_404_NOT_FOUND
            )

        detail = VendorListingDetailService.get_detail(
            listing.id, vendor.id, request=request
        )
        output_serializer = VendorListingDetailSerializer(detail)
        return success_response(
            data=output_serializer.data,
            message="Listing updated successfully — pending re-approval",
            status=status.HTTP_200_OK,
        )


class BrandOptionsView(GenericAPIView):
    """
    GET /api/vehicles/vendor/brands/?search=...
    Unpaginated — brand catalogue is small and bounded, same reasoning
    as PackageTypeOptionsView.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BrandOptionSerializer

    def get(self, request):
        query = request.query_params.get("search")
        queryset = BrandService.search(query)
        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            data=serializer.data,
            message="Brands retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VehicleTypeOptionsView(GenericAPIView):
    """
    GET /api/vehicles/vendor/vehicle-types/?search=...&brand_id=...
    brand_id is optional — when present, narrows to that brand's
    catalogue (the two-step brand -> vehicle type picker). search
    still works standalone, unchanged for any existing caller.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VehicleTypeOptionSerializer
    pagination_class = CustomPagination

    def get(self, request):
        query = request.query_params.get("search")
        raw_brand_id = request.query_params.get("brand_id")
        brand_id = int(raw_brand_id) if raw_brand_id else None
        queryset = VehicleTypeService.search(query, brand_id)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Vehicle types retrieved successfully",
            status=status.HTTP_200_OK,
        )


class PackageTypeOptionsView(GenericAPIView):
    """
    GET /api/vehicles/vendor/package-types/
    Unpaginated — small bounded admin catalog, same reasoning as
    PickupLocationsByCityView.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PackageTypeOptionSerializer

    def get(self, request):
        queryset = PackageTypeService.get_all()
        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            data=serializer.data,
            message="Package types retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VendorScheduleTemplateListCreateView(GenericAPIView):
    """
    GET  /api/vehicles/vendor/schedule-templates/  — vendor's own templates
    POST /api/vehicles/vendor/schedule-templates/  — create a new one
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ScheduleTemplateSerializer

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        templates = ScheduleTemplateService.get_for_vendor(vendor.id)
        serializer = self.get_serializer(templates, many=True)
        return success_response(
            data=serializer.data,
            message="Schedule templates retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        input_serializer = ScheduleTemplateCreateSerializer(data=request.data)
        if not input_serializer.is_valid():
            return error_response(
                message="Invalid schedule data",
                errors=input_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            template = ScheduleTemplateService.create_for_vendor(
                vendor.id,
                input_serializer.validated_data["name"],
                input_serializer.validated_data["days"],
            )
        except IntegrityError:
            return error_response(
                message="A schedule template with this name already exists.",
                status=status.HTTP_409_CONFLICT,
            )
        output_serializer = self.get_serializer(template)
        return success_response(
            data=output_serializer.data,
            message="Schedule template created successfully",
            status=status.HTTP_201_CREATED,
        )


class VendorListingImagesView(GenericAPIView):
    """
    POST /api/vehicles/vendor/fleet/<int:listing_id>/images/
    Multipart upload — one or more files under the 'images' field.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = VendorListingImageDetailSerializer

    def post(self, request, listing_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        files = request.FILES.getlist("images")
        if not files:
            return error_response(
                message="No images provided. Attach one or more files under the 'images' field.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        # NOTE: SubscriptionPlan.max_images_per_listing exists on the
        # model but isn't enforced here yet — would need an extra
        # query to the vendor's current subscription plan. Flagging
        # as a known gap rather than silently skipping it.

        created = VendorListingImageService.add_images(
            listing_id, vendor.id, files, request.user
        )
        if created is None:
            return error_response(
                message="Listing not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        data = [
            {
                "id": img.pk,
                "image_url": request.build_absolute_uri(img.image.url),
                "is_primary": img.is_primary,
                "sort_order": img.sort_order,
            }
            for img in created
        ]
        serializer = self.get_serializer(data, many=True)
        return success_response(
            data=serializer.data,
            message="Images uploaded successfully",
            status=status.HTTP_201_CREATED,
        )


class VendorListingImageDetailView(APIView):
    """
    DELETE /api/vehicles/vendor/fleet/<int:listing_id>/images/<int:image_id>/
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, listing_id: int, image_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        deleted = VendorListingImageService.delete_image(
            listing_id, vendor.id, image_id
        )
        if not deleted:
            return error_response(
                message="Image not found",
                status=status.HTTP_404_NOT_FOUND,
            )
        return success_response(
            data=None,
            message="Image deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class VendorBlockedPeriodListCreateView(GenericAPIView):
    """
    GET  /api/vehicles/vendor/blocks/  — every block across all of the vendor's listings
    POST /api/vehicles/vendor/blocks/  — create a new block
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VendorBlockedPeriodListSerializer
    pagination_class = CustomPagination

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        blocks = VendorBlockedPeriodService.get_for_vendor(vendor.id)
        page = self.paginate_queryset(blocks)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Blocked periods retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = VendorBlockedPeriodCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid block data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            block = VendorBlockedPeriodService.create_block(
                vendor.id, serializer.validated_data
            )
        except ValidationError as e:
            return error_response(
                message="Validation failed",
                errors=e.message_dict if hasattr(e, "message_dict") else str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )
        output_serializer = VendorBlockedPeriodListSerializer(block)
        return success_response(
            data=output_serializer.data,
            message="Block created successfully",
            status=status.HTTP_201_CREATED,
        )


class VendorBlockedPeriodDetailView(GenericAPIView):
    """PATCH /api/vehicles/vendor/blocks/<int:block_id>/ — update dates/count/reason/note"""

    permission_classes = [IsAuthenticated]
    serializer_class = VendorBlockedPeriodUpdateSerializer

    def patch(self, request, block_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = VendorBlockedPeriodUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid block data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            block = VendorBlockedPeriodService.update_block(
                block_id, vendor.id, serializer.validated_data
            )
        except ValidationError as e:
            return error_response(
                message="Validation failed",
                errors=e.message_dict if hasattr(e, "message_dict") else str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if block is None:
            return error_response(
                message="Block not found", status=status.HTTP_404_NOT_FOUND
            )

        output_serializer = VendorBlockedPeriodListSerializer(block)
        return success_response(
            data=output_serializer.data,
            message="Block updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, block_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        deleted = VendorBlockedPeriodService.delete_block(block_id, vendor.id)
        if not deleted:
            return error_response(
                message="Block not found", status=status.HTTP_404_NOT_FOUND
            )
        return success_response(
            data=None,
            message="Block deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class VendorScheduleTemplateDetailView(GenericAPIView):
    """
    GET/PATCH/DELETE /api/vehicles/vendor/schedule-templates/<int:template_id>/

    Delete note: schedule_template is SET_NULL on VehicleListing, so
    this never raises an integrity error — but any listing still
    pointing at a deleted template loses its schedule and becomes
    closed every day per AvailabilityService's fail-safe rule.
    listings_count on the response exists so the frontend can warn
    about this before the vendor confirms.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ScheduleTemplateSerializer

    def get(self, request, template_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        template = ScheduleTemplateService.get_detail_for_vendor(template_id, vendor.id)
        if template is None:
            return error_response(
                message="Schedule template not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(template)
        return success_response(
            data=serializer.data,
            message="Schedule template retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def patch(self, request, template_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        input_serializer = ScheduleTemplateCreateSerializer(data=request.data)
        if not input_serializer.is_valid():
            return error_response(
                message="Invalid schedule data",
                errors=input_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            template = ScheduleTemplateService.update_for_vendor(
                template_id,
                vendor.id,
                input_serializer.validated_data["name"],
                input_serializer.validated_data["days"],
            )
        except IntegrityError:
            return error_response(
                message="A schedule template with this name already exists.",
                status=status.HTTP_409_CONFLICT,
            )
        if template is None:
            return error_response(
                message="Schedule template not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(template)
        return success_response(
            data=serializer.data,
            message="Schedule template updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, template_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        deleted = ScheduleTemplateService.delete_for_vendor(template_id, vendor.id)
        if not deleted:
            return error_response(
                message="Schedule template not found", status=status.HTTP_404_NOT_FOUND
            )
        return success_response(
            data=None,
            message="Schedule template deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class VendorPickupPointListCreateView(GenericAPIView):
    """
    GET  /api/vehicles/vendor/pickup-points/?pickup_location_id=...
    POST /api/vehicles/vendor/pickup-points/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VendorPickupPointSerializer

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        raw_location_id = request.query_params.get("pickup_location_id")
        points = VendorPickupPointService.get_for_vendor(
            vendor.id, int(raw_location_id) if raw_location_id else None
        )
        serializer = self.get_serializer(points, many=True)
        return success_response(
            data=serializer.data,
            message="Pickup points retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = VendorPickupPointSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid pickup point data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            point = VendorPickupPointService.create_for_vendor(
                vendor.id, serializer.validated_data
            )
        except ValidationError as e:
            return error_response(
                message="Validation failed",
                errors=e.message_dict if hasattr(e, "message_dict") else str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )
        output_serializer = self.get_serializer(point)
        return success_response(
            data=output_serializer.data,
            message="Pickup point created successfully",
            status=status.HTTP_201_CREATED,
        )


class VendorPickupPointListCreateView(GenericAPIView):
    """
    GET  /api/vehicles/vendor/pickup-points/?pickup_location_id=...
    POST /api/vehicles/vendor/pickup-points/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VendorPickupPointSerializer

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        raw_location_id = request.query_params.get("pickup_location_id")
        points = VendorPickupPointService.get_for_vendor(
            vendor.id, int(raw_location_id) if raw_location_id else None
        )
        serializer = self.get_serializer(points, many=True)
        return success_response(
            data=serializer.data,
            message="Pickup points retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = VendorPickupPointSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid pickup point data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            point = VendorPickupPointService.create_for_vendor(
                vendor.id, serializer.validated_data
            )
        except ValidationError as e:
            return error_response(
                message="Validation failed",
                errors=e.message_dict if hasattr(e, "message_dict") else str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )
        output_serializer = self.get_serializer(point)
        return success_response(
            data=output_serializer.data,
            message="Pickup point created successfully",
            status=status.HTTP_201_CREATED,
        )


class VendorPickupPointDetailView(GenericAPIView):
    """GET/PATCH/DELETE /api/vehicles/vendor/pickup-points/<int:point_id>/"""

    permission_classes = [IsAuthenticated]
    serializer_class = VendorPickupPointSerializer

    def get(self, request, point_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        point = VendorPickupPointService.get_detail_for_vendor(point_id, vendor.id)
        if point is None:
            return error_response(
                message="Pickup point not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(point)
        return success_response(
            data=serializer.data,
            message="Pickup point retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def patch(self, request, point_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = VendorPickupPointSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                message="Invalid pickup point data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            point = VendorPickupPointService.update_for_vendor(
                point_id, vendor.id, serializer.validated_data
            )
        except ValidationError as e:
            return error_response(
                message="Validation failed",
                errors=e.message_dict if hasattr(e, "message_dict") else str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if point is None:
            return error_response(
                message="Pickup point not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(point)
        return success_response(
            data=serializer.data,
            message="Pickup point updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, point_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )
        deleted = VendorPickupPointService.delete_for_vendor(point_id, vendor.id)
        if not deleted:
            return error_response(
                message="Pickup point not found", status=status.HTTP_404_NOT_FOUND
            )
        return success_response(
            data=None,
            message="Pickup point deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class VendorListingActiveToggleView(GenericAPIView):
    """
    PATCH /api/vehicles/vendor/fleet/<int:listing_id>/toggle-active/
    No request body needed — flips APPROVED<->PAUSED. Powers the
    on/off switch on the vendor's Fleet card.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VendorListingStatusSerializer

    def patch(self, request, listing_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        listing, error = VendorFleetService.toggle_active_status(listing_id, vendor.id)
        if error == "not_found":
            return error_response(
                message="Listing not found", status=status.HTTP_404_NOT_FOUND
            )
        if error == "not_toggleable":
            return error_response(
                message="Only active or paused listings can be toggled this way.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(listing)
        return success_response(
            data=serializer.data,
            message="Listing status updated successfully",
            status=status.HTTP_200_OK,
        )


class AdminListingListView(GenericAPIView):
    """GET /api/vehicles/admin/listings/?status=&vendor_id=&search=&page="""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminListingListSerializer
    pagination_class = CustomPagination

    def get(self, request):
        status_filter = request.query_params.get("status")
        vendor_id = request.query_params.get("vendor_id")
        search = request.query_params.get("search")
        queryset = AdminListingService.get_all(
            status_filter, int(vendor_id) if vendor_id else None, search
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True, context={"request": request})
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Listings retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminListingDetailView(GenericAPIView):
    """GET /api/vehicles/admin/listings/<int:listing_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminListingDetailSerializer

    def get(self, request, listing_id: int):
        data = AdminListingService.get_detail_data(listing_id, request=request)
        if data is None:
            return error_response(
                message="Listing not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = AdminListingDetailSerializer(data)
        return success_response(
            data=serializer.data,
            message="Listing retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminListingStatusUpdateView(GenericAPIView):
    """PATCH /api/vehicles/admin/listings/<int:listing_id>/status/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminListingStatusUpdateSerializer

    def patch(self, request, listing_id: int):
        serializer = AdminListingStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        listing, error = AdminListingService.update_status(
            listing_id,
            serializer.validated_data["status"],
            request.user,
            serializer.validated_data["reason"],
        )
        if listing is None:
            code = (
                status.HTTP_404_NOT_FOUND
                if error == "Listing not found"
                else status.HTTP_400_BAD_REQUEST
            )
            return error_response(message=error, status=code)
        data = AdminListingService.get_detail_data(listing_id, request=request)
        output = AdminListingDetailSerializer(data)
        return success_response(
            data=output.data,
            message="Listing status updated successfully",
            status=status.HTTP_200_OK,
        )


class AdminBrandListCreateView(GenericAPIView):
    """GET/POST /api/vehicles/admin/brands/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminBrandSerializer

    def get(self, request):
        brands = Brand.objects.all().order_by("name")
        serializer = self.get_serializer(brands, many=True)
        return success_response(
            data=serializer.data,
            message="Brands retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminBrandSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminBrandSerializer(instance).data,
            message="Brand created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminBrandDetailView(GenericAPIView):
    """PATCH/DELETE /api/vehicles/admin/brands/<int:brand_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminBrandSerializer

    def patch(self, request, brand_id: int):
        brand = Brand.objects.filter(id=brand_id).first()
        if brand is None:
            return error_response(
                message="Brand not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = AdminBrandSerializer(brand, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminBrandSerializer(instance).data,
            message="Brand updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, brand_id: int):
        brand = Brand.objects.filter(id=brand_id).first()
        if brand is None:
            return error_response(
                message="Brand not found", status=status.HTTP_404_NOT_FOUND
            )
        try:
            brand.delete()
        except ProtectedError:
            return error_response(
                message="This brand has vehicle types under it and can't be deleted.",
                status=status.HTTP_409_CONFLICT,
            )
        return success_response(
            data=None,
            message="Brand deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminVehicleTypeListCreateView(GenericAPIView):
    """GET/POST /api/vehicles/admin/vehicle-types/?search=&brand_id=&page="""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVehicleTypeSerializer
    pagination_class = CustomPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        search = request.query_params.get("search")
        brand_id = request.query_params.get("brand_id")
        qs = VehicleType.objects.select_related("brand").order_by("brand__name", "name")
        if brand_id:
            qs = qs.filter(brand_id=brand_id)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(brand__name__icontains=search))
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True, context={"request": request})
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Vehicle types retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminVehicleTypeSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        output = AdminVehicleTypeSerializer(instance, context={"request": request})
        return success_response(
            data=output.data,
            message="Vehicle type created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminVehicleTypeDetailView(GenericAPIView):
    """GET/PATCH/DELETE /api/vehicles/admin/vehicle-types/<int:vehicle_type_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminVehicleTypeSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, vehicle_type_id: int):
        instance = (
            VehicleType.objects.filter(id=vehicle_type_id)
            .select_related("brand")
            .first()
        )
        if instance is None:
            return error_response(
                message="Vehicle type not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(instance, context={"request": request})
        return success_response(
            data=serializer.data,
            message="Vehicle type retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def patch(self, request, vehicle_type_id: int):
        instance = VehicleType.objects.filter(id=vehicle_type_id).first()
        if instance is None:
            return error_response(
                message="Vehicle type not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = AdminVehicleTypeSerializer(
            instance, data=request.data, partial=True, context={"request": request}
        )
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        output = AdminVehicleTypeSerializer(instance, context={"request": request})
        return success_response(
            data=output.data,
            message="Vehicle type updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, vehicle_type_id: int):
        instance = VehicleType.objects.filter(id=vehicle_type_id).first()
        if instance is None:
            return error_response(
                message="Vehicle type not found", status=status.HTTP_404_NOT_FOUND
            )
        try:
            instance.delete()
        except ProtectedError:
            return error_response(
                message="This vehicle type has listings under it and can't be deleted.",
                status=status.HTTP_409_CONFLICT,
            )
        return success_response(
            data=None,
            message="Vehicle type deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminPackageCategoryListCreateView(GenericAPIView):
    """GET/POST /api/vehicles/admin/package-categories/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminPackageCategorySerializer

    def get(self, request):
        items = PackageCategory.objects.all().order_by("sort_order", "name")
        serializer = self.get_serializer(items, many=True)
        return success_response(
            data=serializer.data,
            message="Package categories retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminPackageCategorySerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminPackageCategorySerializer(instance).data,
            message="Package category created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminPackageCategoryDetailView(GenericAPIView):
    """PATCH/DELETE /api/vehicles/admin/package-categories/<int:category_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminPackageCategorySerializer

    def patch(self, request, category_id: int):
        instance = PackageCategory.objects.filter(id=category_id).first()
        if instance is None:
            return error_response(
                message="Package category not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = AdminPackageCategorySerializer(
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
            data=AdminPackageCategorySerializer(instance).data,
            message="Package category updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, category_id: int):
        instance = PackageCategory.objects.filter(id=category_id).first()
        if instance is None:
            return error_response(
                message="Package category not found", status=status.HTTP_404_NOT_FOUND
            )
        try:
            instance.delete()
        except ProtectedError:
            return error_response(
                message="This category has package types under it and can't be deleted.",
                status=status.HTTP_409_CONFLICT,
            )
        return success_response(
            data=None,
            message="Package category deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


class AdminPricingPackageTypeListCreateView(GenericAPIView):
    """GET/POST /api/vehicles/admin/package-types/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminPricingPackageTypeSerializer

    def get(self, request):
        items = PricingPackageType.objects.select_related("category").order_by(
            "sort_order", "name"
        )
        serializer = self.get_serializer(items, many=True)
        return success_response(
            data=serializer.data,
            message="Package types retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AdminPricingPackageTypeSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = serializer.save()
        return success_response(
            data=AdminPricingPackageTypeSerializer(instance).data,
            message="Package type created successfully",
            status=status.HTTP_201_CREATED,
        )


class AdminPricingPackageTypeDetailView(GenericAPIView):
    """PATCH/DELETE /api/vehicles/admin/package-types/<int:package_type_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminPricingPackageTypeSerializer

    def patch(self, request, package_type_id: int):
        instance = PricingPackageType.objects.filter(id=package_type_id).first()
        if instance is None:
            return error_response(
                message="Package type not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = AdminPricingPackageTypeSerializer(
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
            data=AdminPricingPackageTypeSerializer(instance).data,
            message="Package type updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, package_type_id: int):
        instance = PricingPackageType.objects.filter(id=package_type_id).first()
        if instance is None:
            return error_response(
                message="Package type not found", status=status.HTTP_404_NOT_FOUND
            )
        try:
            instance.delete()
        except ProtectedError:
            return error_response(
                message="This package type is used by one or more listings and can't be deleted.",
                status=status.HTTP_409_CONFLICT,
            )
        return success_response(
            data=None,
            message="Package type deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )
