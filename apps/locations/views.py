# apps/locations/views.py
from rest_framework.generics import GenericAPIView

from rest_framework.response import Response
from rest_framework import status

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from apps.core.pagination import CustomPagination
from apps.locations.filters import CityFilter, StateFilter, PickupLocationFilter
from rest_framework.views import APIView
from django.core.exceptions import ValidationError
from apps.locations.serializers import (
    CountrySerializer, StateSerializer,
    CitySerializer, PickupLocationSerializer
)
from apps.locations.services import (
    CountryService, StateService,
    CityService, PickupLocationService
)


class CountryListCreateView(GenericAPIView):
    serializer_class = CountrySerializer
    pagination_class = CustomPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "code"]
    # ordering = ["name"]

    def get_queryset(self):
        return CountryService.get_all()

    def get(self, request):
        queryset = self.filter_queryset(self.get_queryset())  # applies search/ordering
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        city = CountryService.create(serializer.validated_data)
        return Response(CountrySerializer(city).data, status=status.HTTP_201_CREATED)


class CountryDetailView(APIView):

    def get(self, request, pk):
        try:
            country = CountryService.get_by_id(pk)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(CountrySerializer(country).data)

    def patch(self, request, pk):
        try:
            country = CountryService.update(pk, request.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(CountrySerializer(country).data)

    def delete(self, request, pk):
        try:
            CountryService.delete(pk)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)




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
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        state = StateService.create(serializer.validated_data)
        return Response(StateSerializer(state).data, status=status.HTTP_201_CREATED)


class StateDetailView(APIView):

    def get(self, request, pk):
        try:
            state = StateService.get_by_id(pk)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(StateSerializer(state).data)

    def patch(self, request, pk):
        try:
            state = StateService.update(pk, request.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(StateSerializer(state).data)

    def delete(self, request, pk):
        try:
            StateService.delete(pk)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CityListCreateView(GenericAPIView):
    serializer_class = CitySerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = CityFilter
    search_fields = ["name"]
    ordering_fields = ["name", "state"]
    ordering = ["name"]

    def get_queryset(self):
        return CityService.get_all()

    def get(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        city = CityService.create(serializer.validated_data)
        return Response(CitySerializer(city).data, status=status.HTTP_201_CREATED)


class CityDetailView(APIView):

    def get(self, request, pk):
        try:
            city = CityService.get_by_id(pk)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(CitySerializer(city).data)

    def patch(self, request, pk):
        try:
            city = CityService.update(pk, request.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(CitySerializer(city).data)

    def delete(self, request, pk):
        try:
            CityService.delete(pk)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        location = PickupLocationService.create(serializer.validated_data)
        return Response(PickupLocationSerializer(location).data, status=status.HTTP_201_CREATED)


class PickupLocationDetailView(APIView):

    def get(self, request, pk):
        try:
            location = PickupLocationService.get_by_id(pk)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(PickupLocationSerializer(location).data)

    def patch(self, request, pk):
        try:
            location = PickupLocationService.update(pk, request.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(PickupLocationSerializer(location).data)

    def delete(self, request, pk):
        try:
            PickupLocationService.delete(pk)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)