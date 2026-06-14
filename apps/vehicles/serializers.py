# apps/vehicles/serializers.py

from rest_framework import serializers
from django.utils.dateparse import parse_datetime
from datetime import datetime

from apps.vehicles.models import (
    VehicleListing,
    VehicleType,
    VehicleImage,
    PricingPackage,
)

# ── Query param validation ────────────────────────────────────────────


class VehicleSearchQuerySerializer(serializers.Serializer):
    city_id = serializers.IntegerField(min_value=1)
    pickup_datetime = serializers.DateTimeField()
    dropoff_datetime = serializers.DateTimeField()

    def validate(self, attrs):
        pickup = attrs["pickup_datetime"]
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
        if duration_hours < 3:
            raise serializers.ValidationError("Minimum booking duration is 3 hours.")
        if duration_hours > 8760:
            raise serializers.ValidationError("Booking duration cannot exceed 1 year.")

        return attrs


# ── Response serializers ──────────────────────────────────────────────


class VehicleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleType
        fields = [
            "id",
            "name",
            "primary_image",
            "brand",
            "make_year",
            "transmission_type",
            "fuel_type",
            "seats",
            "cc",
            "mileage_kmpl",
            "vehicle_type",
        ]


class VehicleImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleImage
        fields = ["id", "image", "is_primary", "sort_order"]


class PricingPackageSerializer(serializers.ModelSerializer):
    package_name = serializers.CharField(source="package_type.name")
    category = serializers.CharField(source="package_type.category.name")
    # Use the package_type's duration_hours as the canonical duration
    duration_hours = serializers.DecimalField(
        source="package_type.duration_hours",
        max_digits=5,
        decimal_places=2,
    )

    class Meta:
        model = PricingPackage
        fields = [
            "id",
            "package_name",
            "category",
            "duration_hours",
            "price",
            "pay_at_pickup_enabled",  # now lives on PricingPackage
            "partial_payment_percentage",  # now lives on PricingPackage
        ]


# ── Per-location listing card ─────────────────────────────────────────


class ListingLocationSerializer(serializers.ModelSerializer):
    """
    One entry per vendor+location combination.
    Frontend uses this to populate the location selector on the card.
    """

    location_id = serializers.IntegerField(source="pickup_location.id")
    location_name = serializers.CharField(source="pickup_location.name")
    city_id = serializers.IntegerField(source="pickup_location.city.id")
    city_name = serializers.CharField(source="pickup_location.city.name")
    vendor_id = serializers.IntegerField(source="vendor.id")
    vendor_name = serializers.CharField(source="vendor.business_name")
    images = VehicleImageSerializer(many=True, read_only=True)

    # Daily price surfaced to the top so the card can display it
    # without the frontend having to dig through pricing_packages
    daily_price = serializers.SerializerMethodField()
    pricing_packages = PricingPackageSerializer(many=True, read_only=True)
    pay_at_pickup_enabled = serializers.SerializerMethodField()

    class Meta:
        model = VehicleListing
        fields = [
            "id",  # listing_id — used when initiating booking
            "location_id",
            "location_name",
            "city_id",
            "city_name",
            "vendor_id",
            "vendor_name",
            "daily_price",  # shortcut field for card display
            "available_count",
            "security_deposit_amount",
            "km_limit_per_day",
            "excess_charge_per_km",
            "late_return_penalty_per_hour",
            "doorstep_delivery_enabled",
            "operating_hours_start",
            "operating_hours_end",
            "pricing_packages",  # pay_at_pickup & partial_payment now per-package
            "images",
            "pay_at_pickup_enabled",
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

    def get_pay_at_pickup_enabled(self, listing):
        """
        If any package has pay_at_pickup_enabled=True, we consider the listing as a whole to have that option.
        This simplifies frontend logic, so it doesn't have to check each package.
        """
        for pkg in listing.pricing_packages.all():
            if pkg.pay_at_pickup_enabled:
                return True
        return False


# ── Root search result (one per VehicleType) ──────────────────────────


class VehicleSearchResultSerializer(serializers.ModelSerializer):
    """
    One object per VehicleType.
    `locations` contains every vendor+location listing for that type
    in the searched city — frontend drives the location selector from this.
    """

    locations = serializers.SerializerMethodField()

    class Meta:
        model = VehicleType
        fields = [
            "id",
            "name",
            "brand",
            "make_year",
            "transmission_type",
            "fuel_type",
            "vehicle_type",
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


# ── Vehicle Detail serializers ────────────────────────────────────────


class VehicleDetailImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = VehicleImage
        fields = ["image_url", "is_primary", "sort_order"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url


class VehicleDetailPackageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    price_per_day = serializers.DecimalField(max_digits=10, decimal_places=2)
    label = serializers.CharField()


class FareDetailsSerializer(serializers.Serializer):
    rent_amount = serializers.FloatField()
    total = serializers.FloatField()
    remaining_rent = serializers.FloatField()
    advance_payment = serializers.FloatField()
    refundable_deposit = serializers.FloatField()


class VehiclePickupLocationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    location_name = serializers.CharField()
    exact_address_revealed_after_booking = serializers.BooleanField()
    operating_hours = serializers.CharField()
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)


class VehiclePoliciesSerializer(serializers.Serializer):
    security_deposit = serializers.FloatField()
    distance_limit = serializers.CharField()
    late_penalty_per_hour = serializers.FloatField()
    location_timings = serializers.CharField()
    excess_charge = serializers.CharField()


class VehicleDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()  # listing_id
    name = serializers.CharField()
    make_year = serializers.IntegerField()
    transmission_type = serializers.CharField()
    fuel_type = serializers.CharField()
    seats = serializers.IntegerField()
    cc = serializers.IntegerField()
    mileage_kmpl = serializers.FloatField(allow_null=True)
    top_speed_kmph = serializers.IntegerField(allow_null=True)
    fuel_capacity_litres = serializers.FloatField(allow_null=True)
    kerb_weight_kg = serializers.FloatField(allow_null=True)
    km_limit_per_day = serializers.IntegerField(allow_null=True)
    images = serializers.ListField(child=serializers.CharField())
    primary_image = serializers.CharField(allow_null=True)
    available_count = serializers.IntegerField()
    packages = VehicleDetailPackageSerializer(many=True)
    fare_details = FareDetailsSerializer()
    pickup_location = VehiclePickupLocationSerializer()
    policies = VehiclePoliciesSerializer()
    terms_and_conditions = serializers.ListField(child=serializers.CharField())
    pay_at_pickup_enabled = serializers.BooleanField()


class VehicleReviewItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    author_name = serializers.SerializerMethodField()
    rating = serializers.IntegerField()
    comment = serializers.CharField(source="review_text")
    created_at = serializers.DateTimeField()
    vehicle_name = serializers.SerializerMethodField()

    def get_author_name(self, review):
        customer = review.customer

        if customer.is_anonymised:
            return "Tripzido User"

        first = customer.first_name.strip()
        last = customer.last_name.strip()

        if not first and not last:
            return "Tripzido User"

        if first and last:
            return f"{first} {last[0]}."
        return first or last

    def get_vehicle_name(self, review):
        return review.listing.vehicle_type.name
