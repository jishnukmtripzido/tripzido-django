# apps/vehicles/serializers.py

from rest_framework import serializers
from django.utils.dateparse import parse_datetime
from datetime import datetime

from apps.vehicles.models import (
    VehicleListing, VehicleType,
    VehicleImage, PricingPackage, PricingPackageType
)


# ── Query param validation ────────────────────────────────────────────

class VehicleSearchQuerySerializer(serializers.Serializer):
    city_id          = serializers.IntegerField(min_value=1)
    pickup_datetime  = serializers.DateTimeField()
    dropoff_datetime = serializers.DateTimeField()

    def validate(self, attrs):
        pickup  = attrs["pickup_datetime"]
        dropoff = attrs["dropoff_datetime"]

        now = datetime.now(tz=pickup.tzinfo)

        if pickup < now:
            raise serializers.ValidationError(
                {"pickup_datetime": "Pickup time cannot be in the past."}
            )
        if dropoff <= pickup:
            raise serializers.ValidationError(
                {"dropoff_datetime": "Dropoff must be after pickup."}
            )

        duration_hours = (dropoff - pickup).total_seconds() / 3600
        if duration_hours < 1:
            raise serializers.ValidationError("Minimum booking duration is 1 hour.")
        if duration_hours > 8760:
            raise serializers.ValidationError("Booking duration cannot exceed 1 year.")

        return attrs


# ── Response serializers ──────────────────────────────────────────────

class VehicleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = VehicleType
        fields = [
            "id", "name", "brand", "make_year",
            "transmission_type", "fuel_type",
            "seats", "cc", "mileage_kmpl",
        ]


class VehicleImageSerializer(serializers.ModelSerializer):
    class Meta:
        model  = VehicleImage
        fields = ["id", "image", "is_primary", "sort_order"]


class PricingPackageSerializer(serializers.ModelSerializer):
    package_name     = serializers.CharField(source="package_type.name")
    duration_hours   = serializers.DecimalField(
                            source="package_type.duration_hours",
                            max_digits=5, decimal_places=2
                        )

    class Meta:
        model  = PricingPackage
        fields = ["id", "package_name", "duration_hours", "price"]


class VehicleSearchResultSerializer(serializers.ModelSerializer):
    vehicle_type      = VehicleTypeSerializer(read_only=True)
    images            = VehicleImageSerializer(many=True, read_only=True)
    pricing_packages  = PricingPackageSerializer(many=True, read_only=True)
    location_name     = serializers.CharField(source="pickup_location.name")
    city_name         = serializers.CharField(source="pickup_location.city.name")

    class Meta:
        model  = VehicleListing
        fields = [
            "id",
            "vehicle_type",
            "location_name",
            "city_name",
            "available_count",
            "security_deposit_amount",
            "km_limit_per_day",
            "excess_charge_per_km",
            "late_return_penalty_per_hour",
            "doorstep_delivery_enabled",
            "partial_payment_enabled",
            "partial_payment_percentage",
            "operating_hours_start",
            "operating_hours_end",
            "images",
            "pricing_packages",
        ]