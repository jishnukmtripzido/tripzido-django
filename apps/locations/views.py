from django.shortcuts import render

# Create your views here.
# apps/locations/views.py

from django.core.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.locations.services import (
    CountryService, StateService,
    CityService, PickupLocationService
)
from apps.locations.serializers import (
    CountrySerializer, StateSerializer,
    CitySerializer, PickupLocationSerializer
)


class CountryListCreateView(APIView):

    def get(self, request):
        countries = CountryService.get_all()
        serializer = CountrySerializer(countries, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = CountrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        country = CountryService.create(serializer.validated_data)
        return Response(CountrySerializer(country).data, status=status.HTTP_201_CREATED)


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


# Same pattern for State, City, PickupLocation
class StateListCreateView(APIView):

    def get(self, request):
        states = StateService.get_all()
        return Response(StateSerializer(states, many=True).data)

    def post(self, request):
        serializer = StateSerializer(data=request.data)
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


class CityListCreateView(APIView):

    def get(self, request):
        cities = CityService.get_all()
        return Response(CitySerializer(cities, many=True).data)

    def post(self, request):
        serializer = CitySerializer(data=request.data)
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


class PickupLocationListCreateView(APIView):

    def get(self, request):
        locations = PickupLocationService.get_all()
        return Response(PickupLocationSerializer(locations, many=True).data)

    def post(self, request):
        serializer = PickupLocationSerializer(data=request.data)
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