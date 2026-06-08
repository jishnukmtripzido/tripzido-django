# apps/locations/views.py
from rest_framework.generics import GenericAPIView
from rest_framework import status
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from apps.core.pagination import CustomPagination
from apps.locations.filters import CityFilter, StateFilter, PickupLocationFilter
from rest_framework.views import APIView
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from rest_framework.permissions import AllowAny, IsAuthenticated
from apps.locations.serializers import (
    CountrySerializer,
    StateSerializer,
    CitySerializer,
    PickupLocationSerializer,
)
from apps.locations.services import (
    CountryService,
    StateService,
    CityService,
    PickupLocationService,
)
from apps.core.responses import error_response, success_response

# ─── Country ────────────────────────────────────────────────────────────────


class CountryListCreateView(GenericAPIView):
    serializer_class = CountrySerializer
    pagination_class = CustomPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "code"]

    def get_queryset(self):
        return CountryService.get_all()

    def get(self, request):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                paginated_response = self.get_paginated_response(serializer.data)
                return success_response(
                    data=paginated_response.data,
                    message="Country list retrieved successfully",
                    status=status.HTTP_200_OK,
                )
            serializer = self.get_serializer(queryset, many=True)
            return success_response(
                data=serializer.data,
                message="Country list retrieved successfully",
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return error_response(
                message="Failed to retrieve country list",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation failed",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            country = CountryService.create(serializer.validated_data)
        except Exception as e:
            return error_response(
                message="Failed to create country",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return success_response(
            data=CountrySerializer(country).data,
            message="Country created successfully",
            status=status.HTTP_201_CREATED,
        )


class CountryDetailView(APIView):

    def get(self, request, pk):
        try:
            country = CountryService.get_by_id(pk)
        except ValidationError as e:
            return error_response(
                message="Country not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        return success_response(
            data=CountrySerializer(country).data,
            message="Country retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        try:
            country = CountryService.get_by_id(pk)
        except ValidationError as e:
            return error_response(
                message="Country not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CountrySerializer(country, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                message="Validation failed",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            country = CountryService.update(pk, serializer.validated_data)
        except Exception as e:
            return error_response(
                message="Failed to update country",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return success_response(
            data=CountrySerializer(country).data,
            message="Country updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        try:
            CountryService.delete(pk)
        except ProtectedError:
            return error_response(
                message="Cannot delete this country as it has states associated with it.",
                status=status.HTTP_409_CONFLICT,
            )
        except ValidationError as e:
            return error_response(
                message="Country not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        return success_response(
            data=None,
            message="Country deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


# ─── State ──────────────────────────────────────────────────────────────────


class StateListCreateView(GenericAPIView):
    serializer_class = StateSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = StateFilter
    search_fields = ["name", "code"]
    ordering_fields = ["name"]
    ordering = ["name"]

    def get_queryset(self):
        return StateService.get_all()

    def get(self, request):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                paginated_response = self.get_paginated_response(serializer.data)
                return success_response(
                    data=paginated_response.data,
                    message="State list retrieved successfully",
                    status=status.HTTP_200_OK,
                )
            serializer = self.get_serializer(queryset, many=True)
            return success_response(
                data=serializer.data,
                message="State list retrieved successfully",
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return error_response(
                message="Failed to retrieve state list",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation failed",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            state = StateService.create(serializer.validated_data)
        except Exception as e:
            return error_response(
                message="Failed to create state",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return success_response(
            data=StateSerializer(state).data,
            message="State created successfully",
            status=status.HTTP_201_CREATED,
        )


class StateDetailView(APIView):

    def get(self, request, pk):
        try:
            state = StateService.get_by_id(pk)
        except ValidationError as e:
            return error_response(
                message="State not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        return success_response(
            data=StateSerializer(state).data,
            message="State retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        try:
            state = StateService.get_by_id(pk)
        except ValidationError as e:
            return error_response(
                message="State not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = StateSerializer(state, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                message="Validation failed",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            state = StateService.update(pk, serializer.validated_data)
        except Exception as e:
            return error_response(
                message="Failed to update state",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return success_response(
            data=StateSerializer(state).data,
            message="State updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        try:
            StateService.delete(pk)
        except ProtectedError:
            return error_response(
                message="Cannot delete this state as it has cities associated with it.",
                status=status.HTTP_409_CONFLICT,
            )
        except ValidationError as e:
            return error_response(
                message="State not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        return success_response(
            data=None,
            message="State deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


# ─── City ───────────────────────────────────────────────────────────────────


class CityListCreateView(GenericAPIView):
    serializer_class = CitySerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = CityFilter
    search_fields = ["name"]
    ordering_fields = ["name", "state"]
    ordering = ["name"]

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
        return CityService.get_all()

    def get(self, request):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                paginated_response = self.get_paginated_response(serializer.data)
                return success_response(
                    data=paginated_response.data,
                    message="City list retrieved successfully",
                    status=status.HTTP_200_OK,
                )
            serializer = self.get_serializer(queryset, many=True)
            return success_response(
                data=serializer.data,
                message="City list retrieved successfully",
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return error_response(
                message="Failed to retrieve city list",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation failed",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            city = CityService.create(serializer.validated_data)
        except Exception as e:
            return error_response(
                message="Failed to create city",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return success_response(
            data=CitySerializer(city).data,
            message="City created successfully",
            status=status.HTTP_201_CREATED,
        )


class CityDetailView(APIView):

    def get(self, request, pk):
        try:
            city = CityService.get_by_id(pk)
        except ValidationError as e:
            return error_response(
                message="City not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        return success_response(
            data=CitySerializer(city).data,
            message="City retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        try:
            city = CityService.get_by_id(pk)
        except ValidationError as e:
            return error_response(
                message="City not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CitySerializer(city, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                message="Validation failed",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            city = CityService.update(pk, serializer.validated_data)
        except Exception as e:
            return error_response(
                message="Failed to update city",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return success_response(
            data=CitySerializer(city).data,
            message="City updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        try:
            CityService.delete(pk)
        except ProtectedError:
            return error_response(
                message="Cannot delete this city as it has pickup locations associated with it.",
                status=status.HTTP_409_CONFLICT,
            )
        except ValidationError as e:
            return error_response(
                message="City not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        return success_response(
            data=None,
            message="City deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )


# ─── Pickup Location ─────────────────────────────────────────────────────────


class PickupLocationListCreateView(GenericAPIView):
    serializer_class = PickupLocationSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PickupLocationFilter
    search_fields = ["name", "address"]
    ordering_fields = ["name", "city"]
    ordering = ["name"]

    def get_queryset(self):
        return PickupLocationService.get_all()

    def get(self, request):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                paginated_response = self.get_paginated_response(serializer.data)
                return success_response(
                    data=paginated_response.data,
                    message="Pickup location list retrieved successfully",
                    status=status.HTTP_200_OK,
                )
            serializer = self.get_serializer(queryset, many=True)
            return success_response(
                data=serializer.data,
                message="Pickup location list retrieved successfully",
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return error_response(
                message="Failed to retrieve pickup location list",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation failed",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            location = PickupLocationService.create(serializer.validated_data)
        except Exception as e:
            return error_response(
                message="Failed to create pickup location",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return success_response(
            data=PickupLocationSerializer(location).data,
            message="Pickup location created successfully",
            status=status.HTTP_201_CREATED,
        )


class PickupLocationDetailView(APIView):

    def get(self, request, pk):
        try:
            location = PickupLocationService.get_by_id(pk)
        except ValidationError as e:
            return error_response(
                message="Pickup location not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        return success_response(
            data=PickupLocationSerializer(location).data,
            message="Pickup location retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        try:
            location = PickupLocationService.get_by_id(pk)
        except ValidationError as e:
            return error_response(
                message="Pickup location not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = PickupLocationSerializer(location, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                message="Validation failed",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            location = PickupLocationService.update(pk, serializer.validated_data)
        except Exception as e:
            return error_response(
                message="Failed to update pickup location",
                errors=str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return success_response(
            data=PickupLocationSerializer(location).data,
            message="Pickup location updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        try:
            PickupLocationService.delete(pk)
        except ProtectedError:
            return error_response(
                message="Cannot delete this pickup location as it has vehicles associated with it.",
                status=status.HTTP_409_CONFLICT,
            )
        except ValidationError as e:
            return error_response(
                message="Pickup location not found",
                errors=str(e),
                status=status.HTTP_404_NOT_FOUND,
            )
        return success_response(
            data=None,
            message="Pickup location deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )
