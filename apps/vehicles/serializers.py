# apps/vehicles/serializers.py

from rest_framework import serializers
from django.utils.dateparse import parse_datetime
from datetime import datetime

from apps.vehicles.models import (
    VehicleListing, VehicleType,
    VehicleImage, PricingPackage,
)


# ── Query param validation ────────────────────────────────────────────

class VehicleSearchQuerySerializer(serializers.Serializer):
    city_id          = serializers.IntegerField(min_value=1)
    pickup_datetime  = serializers.DateTimeField()
    dropoff_datetime = serializers.DateTimeField()

    def validate(self, attrs):
        pickup  = attrs["pickup_datetime"]
        dropoff = attrs["dropoff_datetime"]
        now     = datetime.now(tz=pickup.tzinfo)

        if pickup < now:
            raise serializers.ValidationError(
                {"pickup_datetime": "Pickup time cannot be in the past."}
            )
        if dropoff <= pickup:
            raise serializers.ValidationError(
                {"dropoff_datetime": "Dropoff must be after pickup."}
            )

        duration_hours = (dropoff - pickup).total_seconds() / 3600
        if duration_hours < 3:
            raise serializers.ValidationError("Minimum booking duration is 3 hours.")
        if duration_hours > 8760:
            raise serializers.ValidationError("Booking duration cannot exceed 1 year.")

        return attrs


# ── Response serializers ──────────────────────────────────────────────

class VehicleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = VehicleType
        fields = [
            "id", "name", "primary_image", "brand", "make_year",
            "transmission_type", "fuel_type",
            "seats", "cc", "mileage_kmpl",
        ]


class VehicleImageSerializer(serializers.ModelSerializer):
    class Meta:
        model  = VehicleImage
        fields = ["id", "image", "is_primary", "sort_order"]


class PricingPackageSerializer(serializers.ModelSerializer):
    package_name   = serializers.CharField(source="package_type.name")
    category       = serializers.CharField(source="package_type.category.name")
    # Use the package_type's duration_hours as the canonical duration
    duration_hours = serializers.DecimalField(
        source="package_type.duration_hours",
        max_digits=5,
        decimal_places=2,
    )

    class Meta:
        model  = PricingPackage
        fields = [
            "id",
            "package_name",
            "category",
            "duration_hours",
            "price",
            "pay_at_pickup_enabled",       # now lives on PricingPackage
            "partial_payment_percentage",  # now lives on PricingPackage
        ]


# ── Per-location listing card ─────────────────────────────────────────

class ListingLocationSerializer(serializers.ModelSerializer):
    """
    One entry per vendor+location combination.
    Frontend uses this to populate the location selector on the card.
    """
    location_id   = serializers.IntegerField(source="pickup_location.id")
    location_name = serializers.CharField(source="pickup_location.name")
    city_id       = serializers.IntegerField(source="pickup_location.city.id")
    city_name     = serializers.CharField(source="pickup_location.city.name")
    vendor_id     = serializers.IntegerField(source="vendor.id")
    vendor_name   = serializers.CharField(source="vendor.business_name")
    images        = VehicleImageSerializer(many=True, read_only=True)

    # Daily price surfaced to the top so the card can display it
    # without the frontend having to dig through pricing_packages
    daily_price      = serializers.SerializerMethodField()
    pricing_packages = PricingPackageSerializer(many=True, read_only=True)

    class Meta:
        model  = VehicleListing
        fields = [
            "id",                           # listing_id — used when initiating booking
            "location_id",
            "location_name",
            "city_id",
            "city_name",
            "vendor_id",
            "vendor_name",
            "daily_price",                  # shortcut field for card display
            "available_count",
            "security_deposit_amount",
            "km_limit_per_day",
            "excess_charge_per_km",
            "late_return_penalty_per_hour",
            "doorstep_delivery_enabled",
            "operating_hours_start",
            "operating_hours_end",
            "pricing_packages",             # pay_at_pickup & partial_payment now per-package
            "images",
        ]

    def get_daily_price(self, listing):
        """
        Picks the first package whose category name is 'Daily'.
        All packages are already prefetched — no extra query.
        """
        for pkg in listing.pricing_packages.all():
            if pkg.package_type.category.name.lower() == "daily":
                return str(pkg.price)
        return None


# ── Root search result (one per VehicleType) ──────────────────────────

class VehicleSearchResultSerializer(serializers.ModelSerializer):
    """
    One object per VehicleType.
    `locations` contains every vendor+location listing for that type
    in the searched city — frontend drives the location selector from this.
    """
    locations = serializers.SerializerMethodField()

    class Meta:
        model  = VehicleType
        fields = [
            "id",
            "name",
            "brand",
            "make_year",
            "transmission_type",
            "fuel_type",
            "seats",
            "cc",
            "mileage_kmpl",
            "primary_image",
            "locations",
        ]

    def get_locations(self, vehicle_type):
        # city_listings is set by Prefetch(to_attr="city_listings") in the repo
        # Falls back to empty list if called outside search context
        listings = getattr(vehicle_type, "city_listings", [])
        return ListingLocationSerializer(listings, many=True).data