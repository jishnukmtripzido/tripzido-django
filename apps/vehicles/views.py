# apps/vehicles/views.py

from rest_framework.generics import GenericAPIView
from rest_framework import status
from django.core.exceptions import ValidationError

from apps.vehicles.serializers import (
    VehicleSearchQuerySerializer,
    VehicleSearchResultSerializer,
)
from apps.vehicles.services import VehicleSearchService
from apps.core.responses import success_response, error_response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes


class VehicleSearchView(GenericAPIView):
    serializer_class = VehicleSearchResultSerializer

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
        # 1. Validate query params
        query_serializer = VehicleSearchQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            return error_response(
                message="Invalid search parameters",
                errors=query_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # 2. Call service directly (no get_queryset needed here)
            listings = VehicleSearchService.search(
                city_id=query_serializer.validated_data["city_id"],
                pickup_datetime=query_serializer.validated_data["pickup_datetime"],
                dropoff_datetime=query_serializer.validated_data["dropoff_datetime"],
            )

            # 3. Serialize
            serializer = self.get_serializer(listings, many=True)

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