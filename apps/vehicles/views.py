# apps/vehicles/views.py

from rest_framework.generics import GenericAPIView
from rest_framework import status
from django.core.exceptions import ValidationError

from apps.vehicles.serializers import (
    VehicleSearchQuerySerializer,
    VehicleSearchResultSerializer,
    VehicleReviewItemSerializer,
    VehicleDetailSerializer,
    CheckoutSummaryQuerySerializer,
    CheckoutSummarySerializer,
    LocationTimingSerializer,
)
from apps.vehicles.services import (
    VehicleSearchService,
    VehicleReviewService,
    VehicleReviewService,
    VehicleDetailService,
    LocationTimingService,
)
from apps.core.responses import success_response, error_response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.permissions import AllowAny, IsAuthenticated
from apps.core.pagination import CustomPagination


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
