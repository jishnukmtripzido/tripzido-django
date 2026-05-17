# apps/locations/serializers.py

from rest_framework import serializers
from apps.locations.models import Country, State, City, PickupLocation


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["id", "name", "code"]


class StateSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = State
        fields = ["id", "name", "code", "country", "country_name"]


class CitySerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="state.name", read_only=True)
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = City
        fields = ["id", "name", "state", "state_name", "country", "country_name", "city_image"]


class PickupLocationSerializer(serializers.ModelSerializer):
    city_name = serializers.CharField(source="city.name", read_only=True)

    class Meta:
        model = PickupLocation
        fields = ["id", "name", "address", "latitude", "longitude", "city", "city_name"]