# apps/vehicles/serializers.py

from rest_framework import serializers
from django.utils.dateparse import parse_datetime
from datetime import datetime
from decimal import Decimal

from apps.vehicles.models import (
    Brand,
    PackageCategory,
    VehicleListing,
    VehicleType,
    VehicleImage,
    PricingPackage,
    PricingPackageType,
    ListingBlockedPeriod,
    VendorPickupPoint,
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
    brand = serializers.CharField(source="brand.name", read_only=True)

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
    brand = serializers.CharField(source="brand.name", read_only=True)

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


class VendorFleetListingSerializer(serializers.ModelSerializer):
    """
    One row per VehicleListing, for the vendor's own Fleet screen.
    Deliberately NOT grouped by VehicleType like
    VehicleSearchResultSerializer/ListingLocationSerializer — those
    group listings for marketplace browsing, but here the vendor is
    managing individual units they own, so each listing is its own row.
    """

    name = serializers.CharField(source="vehicle_type.name")
    brand = serializers.CharField(source="vehicle_type.brand.name")
    vehicle_type = serializers.CharField(source="vehicle_type.vehicle_type")
    location_name = serializers.CharField(source="pickup_location.name")
    quantity = serializers.IntegerField(source="available_count")
    primary_image = serializers.SerializerMethodField()
    pickup_point_label = serializers.SerializerMethodField()

    class Meta:
        model = VehicleListing
        fields = [
            "id",
            "name",
            "brand",
            "vehicle_type",
            "location_name",
            "quantity",
            "status",
            "primary_image",
            "pickup_point_label",
        ]

    def get_primary_image(self, listing):
        request = self.context.get("request")
        # List rows always show the catalog VehicleType photo — every
        # listing of "Yamaha Fascino" looks identical in the list
        # regardless of which unit has vendor-uploaded photos attached.
        # Falls back to the listing's own uploaded image only if the
        # catalog entry itself has no photo (an incomplete admin entry,
        # not something a vendor should ever hit in practice).
        if listing.vehicle_type.primary_image:
            url = listing.vehicle_type.primary_image.url
        else:
            images = list(listing.images.all())  # already prefetched — no extra query
            image = next((img for img in images if img.is_primary), None) or (
                images[0] if images else None
            )
            if image is None:
                return None
            url = image.image.url
        return request.build_absolute_uri(url) if request else url

    def get_pickup_point_label(self, listing):
        point = listing.pickup_point
        return point.label or point.address[:40] if point else None


class VendorListingVehicleTypeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    brand = serializers.CharField()
    make_year = serializers.IntegerField()
    transmission_type = serializers.CharField()
    fuel_type = serializers.CharField()
    vehicle_type = serializers.CharField()
    seats = serializers.IntegerField()
    cc = serializers.IntegerField()
    mileage_kmpl = serializers.FloatField(allow_null=True)
    top_speed_kmph = serializers.IntegerField(allow_null=True)
    fuel_capacity_litres = serializers.FloatField(allow_null=True)
    weight_kg = serializers.FloatField(allow_null=True)
    primary_image = serializers.CharField(allow_null=True)


class VendorListingPickupLocationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField(allow_blank=True)
    city_id = serializers.IntegerField()
    city_name = serializers.CharField()
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)


class VendorListingImageDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    image_url = serializers.CharField(allow_null=True)
    is_primary = serializers.BooleanField()
    sort_order = serializers.IntegerField()


class VendorListingPackageDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    package_type_id = serializers.IntegerField()  # NEW
    name = serializers.CharField()
    category = serializers.CharField()
    duration_hours = serializers.DecimalField(max_digits=5, decimal_places=2)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    pay_at_pickup_enabled = serializers.BooleanField()
    partial_payment_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, allow_null=True
    )
    km_limit = serializers.IntegerField(allow_null=True)


class VendorListingScheduleDaySerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField()
    day_name = serializers.CharField()
    is_closed = serializers.BooleanField()
    open_time = serializers.CharField(allow_null=True)
    close_time = serializers.CharField(allow_null=True)
    timing = serializers.CharField()


class VendorListingScheduleSerializer(serializers.Serializer):
    has_schedule = serializers.BooleanField()
    id = serializers.IntegerField(allow_null=True)  # NEW
    template_name = serializers.CharField(allow_null=True)
    days = VendorListingScheduleDaySerializer(many=True)


class VendorListingPoliciesSerializer(serializers.Serializer):
    security_deposit_amount = serializers.FloatField()
    km_limit_per_day = serializers.IntegerField(allow_null=True)
    excess_charge_per_km = serializers.FloatField(allow_null=True)
    late_return_penalty_per_hour = serializers.FloatField(allow_null=True)
    doorstep_delivery_enabled = serializers.BooleanField()
    operating_hours_start = serializers.CharField(allow_null=True)
    operating_hours_end = serializers.CharField(allow_null=True)


class VendorListingDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    rejection_reason = serializers.CharField(allow_blank=True)
    available_count = serializers.IntegerField()
    vehicle_type = VendorListingVehicleTypeSerializer()
    pickup_location = VendorListingPickupLocationSerializer()
    images = VendorListingImageDetailSerializer(many=True)
    pricing_packages = VendorListingPackageDetailSerializer(many=True)
    schedule = VendorListingScheduleSerializer()
    policies = VendorListingPoliciesSerializer()
    created_at = serializers.DateTimeField()


class VehicleTypeOptionSerializer(serializers.ModelSerializer):
    brand = serializers.CharField(source="brand.name", read_only=True)
    brand_id = serializers.IntegerField(source="brand.id", read_only=True)

    class Meta:
        model = VehicleType
        fields = [
            "id",
            "name",
            "brand",
            "brand_id",
            "make_year",
            "transmission_type",
            "fuel_type",
            "vehicle_type",
            "seats",
            "cc",
            "primary_image",
        ]


class BrandOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name"]


class PackageTypeOptionSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="category.name")

    class Meta:
        model = PricingPackageType
        fields = ["id", "name", "category", "duration_hours"]


class ScheduleTemplateDayInputSerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField(min_value=0, max_value=6)
    is_closed = serializers.BooleanField(default=False)
    open_time = serializers.TimeField(required=False, allow_null=True)
    close_time = serializers.TimeField(required=False, allow_null=True)


class ScheduleTemplateCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    days = ScheduleTemplateDayInputSerializer(many=True)

    def validate_days(self, value):
        seen = {d["day_of_week"] for d in value}
        if len(seen) != len(value):
            raise serializers.ValidationError("Duplicate day_of_week entries.")
        return value


class ScheduleTemplateDayOutputSerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField()
    is_closed = serializers.BooleanField()
    open_time = serializers.TimeField(allow_null=True)
    close_time = serializers.TimeField(allow_null=True)


class ScheduleTemplateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    listings_count = serializers.SerializerMethodField()
    days = serializers.SerializerMethodField()

    def get_listings_count(self, template):
        # 0 for a template that was just created in-memory (not yet
        # re-fetched via the annotated queryset) — correct either way,
        # since a brand-new template genuinely has zero listings.
        return getattr(template, "listings_count", 0)

    def get_days(self, template):
        days = getattr(template, "ordered_days", [])
        return ScheduleTemplateDayOutputSerializer(days, many=True).data


class VendorPricingPackageInputSerializer(serializers.Serializer):
    package_type_id = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    pay_at_pickup_enabled = serializers.BooleanField(default=False)
    partial_payment_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True
    )
    km_limit = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class VendorListingCreateSerializer(serializers.Serializer):
    vehicle_type_id = serializers.IntegerField()
    pickup_location_id = serializers.IntegerField()
    schedule_template_id = serializers.IntegerField()
    available_count = serializers.IntegerField(min_value=1, default=1)
    pickup_point_id = serializers.IntegerField()
    security_deposit_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, default=0
    )
    km_limit_per_day = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    excess_charge_per_km = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    late_return_penalty_per_hour = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    doorstep_delivery_enabled = serializers.BooleanField(default=False)
    operating_hours_start = serializers.TimeField(required=False, allow_null=True)
    operating_hours_end = serializers.TimeField(required=False, allow_null=True)
    pricing_packages = VendorPricingPackageInputSerializer(many=True)

    def validate_pricing_packages(self, value):
        if not value:
            raise serializers.ValidationError(
                "At least one pricing package is required."
            )
        ids = [p["package_type_id"] for p in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                "Duplicate package_type_id in pricing_packages."
            )
        return value


class VendorListingUpdateSerializer(serializers.Serializer):
    pickup_location_id = serializers.IntegerField()
    schedule_template_id = serializers.IntegerField()
    pickup_point_id = serializers.IntegerField()
    available_count = serializers.IntegerField(min_value=1, default=1)
    security_deposit_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, default=0
    )
    km_limit_per_day = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    excess_charge_per_km = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    late_return_penalty_per_hour = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    doorstep_delivery_enabled = serializers.BooleanField(default=False)
    operating_hours_start = serializers.TimeField(required=False, allow_null=True)
    operating_hours_end = serializers.TimeField(required=False, allow_null=True)
    pricing_packages = VendorPricingPackageInputSerializer(many=True)

    def validate_pricing_packages(self, value):
        if not value:
            raise serializers.ValidationError(
                "At least one pricing package is required."
            )
        ids = [p["package_type_id"] for p in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                "Duplicate package_type_id in pricing_packages."
            )
        return value


class VendorBlockedPeriodListSerializer(serializers.ModelSerializer):
    vehicle_name = serializers.CharField(source="listing.vehicle_type.name")
    location_name = serializers.CharField(source="listing.pickup_location.name")
    listing_id = serializers.IntegerField(source="listing.id")
    listing_available_count = serializers.IntegerField(source="listing.available_count")
    reason_label = serializers.CharField(source="get_reason_display")
    is_indefinite = serializers.BooleanField(read_only=True)  # ← source= removed

    class Meta:
        model = ListingBlockedPeriod
        fields = [
            "id",
            "listing_id",
            "vehicle_name",
            "location_name",
            "start_datetime",
            "end_datetime",
            "is_indefinite",
            "count",
            "listing_available_count",
            "reason",
            "reason_label",
            "note",
            "created_at",
        ]


class VendorBlockedPeriodCreateSerializer(serializers.Serializer):
    listing_id = serializers.IntegerField()
    start_datetime = serializers.DateTimeField()
    end_datetime = serializers.DateTimeField(
        required=False, allow_null=True, default=None
    )
    count = serializers.IntegerField(min_value=1)
    reason = serializers.ChoiceField(
        choices=ListingBlockedPeriod.BlockReason.choices, default="OTHER"
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        end = attrs.get("end_datetime")
        if end is not None and end <= attrs["start_datetime"]:
            raise serializers.ValidationError(
                {"end_datetime": "End date/time must be after start date/time."}
            )
        return attrs


class VendorBlockedPeriodUpdateSerializer(serializers.Serializer):
    start_datetime = serializers.DateTimeField()
    end_datetime = serializers.DateTimeField(
        required=False, allow_null=True, default=None
    )
    count = serializers.IntegerField(min_value=1)
    reason = serializers.ChoiceField(
        choices=ListingBlockedPeriod.BlockReason.choices, required=False
    )
    note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        end = attrs.get("end_datetime")
        if end is not None and end <= attrs["start_datetime"]:
            raise serializers.ValidationError(
                {"end_datetime": "End date/time must be after start date/time."}
            )
        return attrs


class VendorPickupPointSerializer(serializers.ModelSerializer):
    pickup_location_name = serializers.CharField(
        source="pickup_location.name", read_only=True, allow_null=True
    )

    class Meta:
        model = VendorPickupPoint
        fields = [
            "id",
            "pickup_location",
            "pickup_location_name",
            "label",
            "address",
            "contact_numbers",
            "latitude",
            "longitude",
            "google_maps_link",
        ]

    def validate_contact_numbers(self, value):
        if not isinstance(value, list) or not (1 <= len(value) <= 3):
            raise serializers.ValidationError(
                "Provide between 1 and 3 contact numbers."
            )
        for n in value:
            if not isinstance(n, str) or not n.strip():
                raise serializers.ValidationError(
                    "Each contact number must be a non-empty string."
                )
        return value


class VendorListingPickupPointSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.CharField(allow_blank=True)
    address = serializers.CharField()
    contact_numbers = serializers.ListField(child=serializers.CharField())
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    google_maps_link = serializers.CharField(allow_blank=True)


class VendorListingDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    rejection_reason = serializers.CharField(allow_blank=True)
    available_count = serializers.IntegerField()
    vehicle_type = VendorListingVehicleTypeSerializer()
    pickup_location = VendorListingPickupLocationSerializer()
    pickup_point = VendorListingPickupPointSerializer(allow_null=True)  # NEW
    images = VendorListingImageDetailSerializer(many=True)
    pricing_packages = VendorListingPackageDetailSerializer(many=True)
    schedule = VendorListingScheduleSerializer()
    policies = VendorListingPoliciesSerializer()
    created_at = serializers.DateTimeField()


class VendorListingStatusSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    status_label = serializers.SerializerMethodField()

    def get_status_label(self, obj):
        return obj.get_status_display()


class AdminListingListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    vendor_name = serializers.CharField(source="vendor.business_name")
    vehicle_type_name = serializers.SerializerMethodField()
    vehicle_type_image = serializers.SerializerMethodField()
    location_name = serializers.CharField(source="pickup_location.name")
    quantity = serializers.IntegerField(source="available_count")
    status = serializers.CharField()
    status_label = serializers.CharField(source="get_status_display")
    created_at = serializers.DateTimeField()

    def get_vehicle_type_name(self, obj):
        return f"{obj.vehicle_type.brand.name} {obj.vehicle_type.name}"

    def get_vehicle_type_image(self, obj):
        request = self.context.get("request")
        if not obj.vehicle_type.primary_image:
            return None
        url = obj.vehicle_type.primary_image.url
        return request.build_absolute_uri(url) if request else url


class AdminListingImageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    image_url = serializers.CharField(allow_null=True)
    is_primary = serializers.BooleanField()
    sort_order = serializers.IntegerField()


class AdminListingPackageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    category = serializers.CharField()
    duration_hours = serializers.DecimalField(max_digits=5, decimal_places=2)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    pay_at_pickup_enabled = serializers.BooleanField()
    km_limit = serializers.IntegerField(allow_null=True)


class AdminListingScheduleDaySerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField()
    is_closed = serializers.BooleanField()
    timing = serializers.CharField()


class AdminListingDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    rejection_reason = serializers.CharField(allow_blank=True)
    suspension_reason = serializers.CharField(allow_blank=True)
    available_count = serializers.IntegerField()
    vendor_id = serializers.IntegerField()
    vendor_name = serializers.CharField()
    vehicle_type_id = serializers.IntegerField()
    vehicle_type_name = serializers.CharField()
    vehicle_type_image = serializers.CharField(allow_null=True)
    pickup_location_name = serializers.CharField()
    pickup_point_address = serializers.CharField(allow_null=True)
    schedule_template_name = serializers.CharField(allow_null=True)
    schedule_days = AdminListingScheduleDaySerializer(many=True)
    images = AdminListingImageSerializer(many=True)
    pricing_packages = AdminListingPackageSerializer(many=True)
    security_deposit_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    km_limit_per_day = serializers.IntegerField(allow_null=True)
    excess_charge_per_km = serializers.DecimalField(
        max_digits=8, decimal_places=2, allow_null=True
    )
    late_return_penalty_per_hour = serializers.DecimalField(
        max_digits=8, decimal_places=2, allow_null=True
    )
    doorstep_delivery_enabled = serializers.BooleanField()
    approved_by_name = serializers.CharField(allow_null=True)
    approved_at = serializers.DateTimeField(allow_null=True)
    suspended_by_name = serializers.CharField(allow_null=True)
    suspended_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class AdminListingStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=VehicleListing.Status.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AdminBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name"]


class AdminVehicleTypeSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source="brand.name", read_only=True)

    class Meta:
        model = VehicleType
        fields = [
            "id",
            "name",
            "brand",
            "brand_name",
            "make_year",
            "transmission_type",
            "vehicle_type",
            "fuel_type",
            "primary_image",
            "seats",
            "cc",
            "top_speed_kmph",
            "fuel_capacity_litres",
            "weight_kg",
            "mileage_kmpl",
            "is_published",
        ]


class AdminPackageCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PackageCategory
        fields = ["id", "name", "description", "sort_order"]


class AdminPricingPackageTypeSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = PricingPackageType
        fields = [
            "id",
            "category",
            "category_name",
            "name",
            "description",
            "duration_hours",
            "sort_order",
        ]
