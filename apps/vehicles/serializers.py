# apps/vehicles/serializers.py

from rest_framework import serializers
from django.utils.dateparse import parse_datetime
from datetime import datetime
from decimal import Decimal

from apps.vehicles.models import (
    VehicleListing,
    VehicleType,
    VehicleImage,
    PricingPackage,
)
from apps.vehicles.utils import format_duration

# ── Query param validation ────────────────────────────────────────────


class VehicleSearchQuerySerializer(serializers.Serializer):
    city_id = serializers.IntegerField(min_value=1)
    pickup_datetime = serializers.DateTimeField()
    dropoff_datetime = serializers.DateTimeField()
    vehicle_type_id = serializers.IntegerField(min_value=1, required=False)

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
    duration_hours = serializers.DecimalField(
        source="package_type.duration_hours",
        max_digits=5,
        decimal_places=2,
    )
    total_price = serializers.SerializerMethodField()
    total_km_limit = serializers.SerializerMethodField()
    total_duration = serializers.SerializerMethodField()

    class Meta:
        model = PricingPackage
        fields = [
            "id",
            "package_name",
            "category",
            "duration_hours",
            "price",
            "total_price",
            "pay_at_pickup_enabled",
            "partial_payment_percentage",
            "km_limit",
            "total_km_limit",
            "total_duration",
        ]

    def _multiplier(self, obj) -> Decimal:
        # Set in VehicleSearchService.search(); defaults to 1 if this
        # serializer is ever reused outside that flow.
        return getattr(obj, "matched_multiplier", Decimal("1"))

    def get_total_price(self, obj):
        return str(obj.price * self._multiplier(obj))

    def get_total_km_limit(self, obj):
        if not obj.km_limit:
            return "No Distance Limit"
        return f"{int(obj.km_limit * self._multiplier(obj))} km included"

    def get_total_duration(self, obj):
        hours = getattr(obj, "searched_duration_hours", None)
        return format_duration(hours) if hours is not None else None


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
    pricing_packages = serializers.SerializerMethodField()
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

    def get_pricing_packages(self, listing):
        pkg = getattr(listing, "matched_package", None)
        if pkg is None:
            return []
        return PricingPackageSerializer([pkg], many=True).data

    def get_daily_price(self, listing):
        pkg = getattr(listing, "matched_package", None)
        if pkg and pkg.package_type.category.name.lower() == "daily":
            return str(pkg.price)
        return None

    def get_pay_at_pickup_enabled(self, listing):
        pkg = getattr(listing, "matched_package", None)
        return bool(pkg and pkg.pay_at_pickup_enabled)


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
    category = serializers.CharField()
    duration_hours = serializers.DecimalField(max_digits=5, decimal_places=2)
    price_per_day = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    km_limit = serializers.IntegerField(allow_null=True)
    total_km_limit = serializers.CharField()
    label = serializers.CharField()
    is_default = serializers.BooleanField()
    partial_payment_percentage = serializers.FloatField(allow_null=True)


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
    id = serializers.IntegerField()
    vehicle_type_id = serializers.IntegerField()
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
    selected_package_id = serializers.IntegerField(allow_null=True)
    requested_package_unavailable = serializers.BooleanField()
    searched_duration = serializers.CharField(allow_null=True)
    fare_details = FareDetailsSerializer()
    pickup_location = VehiclePickupLocationSerializer()
    policies = VehiclePoliciesSerializer()
    terms_and_conditions = serializers.ListField(child=serializers.CharField())
    pay_at_pickup_enabled = serializers.BooleanField()
    is_available = serializers.BooleanField()
    availability_message = serializers.CharField(allow_null=True)
    availability_checked = serializers.BooleanField()


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


class CheckoutSummaryQuerySerializer(serializers.Serializer):
    listing_id = serializers.IntegerField(min_value=1)
    package_id = serializers.IntegerField(min_value=1)
    pickup_datetime = serializers.DateTimeField()
    dropoff_datetime = serializers.DateTimeField()

    def validate(self, attrs):
        if attrs["dropoff_datetime"] <= attrs["pickup_datetime"]:
            raise serializers.ValidationError(
                {"dropoff_datetime": "Dropoff must be after pickup."}
            )
        return attrs


class ThingsToRememberSerializer(serializers.Serializer):
    km_limit = serializers.CharField()
    excess_charge = serializers.CharField()
    location_timings = serializers.CharField()
    late_penalty_per_hour = serializers.FloatField()


class CheckoutSummarySerializer(serializers.Serializer):
    listing_id = serializers.IntegerField()
    package_id = serializers.IntegerField()
    package_name = serializers.CharField()
    vehicle_name = serializers.CharField()
    primary_image = serializers.CharField(allow_null=True)
    available_count = serializers.IntegerField()
    unit_rent_amount = serializers.FloatField()
    unit_refundable_deposit = serializers.FloatField()
    can_pay_partial = serializers.BooleanField()
    partial_payment_percentage = serializers.FloatField(allow_null=True)
    pickup_datetime = serializers.CharField()
    dropoff_datetime = serializers.CharField()
    duration_label = serializers.CharField()
    pickup_location_name = serializers.CharField()
    vendor_id = serializers.IntegerField()  # NEW
    vendor_name = serializers.CharField()  # NEW
    vendor_terms = serializers.ListField(child=serializers.CharField())  # NEW
    things_to_remember = ThingsToRememberSerializer()


class LocationTimingDaySerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField()
    day_name = serializers.CharField()
    is_closed = serializers.BooleanField()
    timing = serializers.CharField()


class LocationTimingSerializer(serializers.Serializer):
    has_schedule = serializers.BooleanField()
    days = LocationTimingDaySerializer(many=True)
