from rest_framework import serializers

from apps.administrations.models import (
    PlatformConfig,
    TaxRate,
    Offer,
    PopularRental,
    AnnouncementBanner,
    LegalDocument,
    CancellationPolicy,
    CancellationTier,
)
from apps.bookings.serializers import AdminBookingListSerializer

# ── Cancellation Policy ───────────────────────────────────────────────


class CancellationTierSerializer(serializers.Serializer):
    hours_before_pickup = serializers.IntegerField()
    refund_percentage = serializers.IntegerField()
    label = serializers.CharField()
    description = serializers.CharField()


class CancellationPolicySerializer(serializers.Serializer):
    full_payment_rules = CancellationTierSerializer(many=True)
    partial_payment_rules = CancellationTierSerializer(many=True)
    note = serializers.CharField()


# ── Offers ────────────────────────────────────────────────────────────


class OfferSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    icon_type = serializers.CharField()
    coupon_code = serializers.CharField()
    discount_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    min_order_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    valid_from = serializers.DateTimeField(allow_null=True)
    valid_until = serializers.DateTimeField(allow_null=True)
    sort_order = serializers.IntegerField()
    is_featured = serializers.SerializerMethodField()

    def get_is_featured(self, obj) -> bool:
        # Annotated by OfferService.get_offers(); defaults to False if
        # this serializer is ever reused outside that flow.
        return getattr(obj, "is_featured", False)


# ── Popular Rentals ───────────────────────────────────────────────────


class PopularRentalQuerySerializer(serializers.Serializer):
    city_id = serializers.IntegerField(min_value=1)


class PopularRentalSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    city_id = serializers.SerializerMethodField()
    city_name = serializers.SerializerMethodField()
    vehicle_type_id = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()
    vehicle_type_category = serializers.SerializerMethodField()
    fuel_type = serializers.SerializerMethodField()
    transmission_type = serializers.SerializerMethodField()
    seats = serializers.SerializerMethodField()
    display_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    image_url = serializers.SerializerMethodField()
    tag = serializers.CharField()
    sort_order = serializers.IntegerField()
    pickup_location_id = serializers.SerializerMethodField()  # new
    pickup_location_name = serializers.SerializerMethodField()  # new

    def get_city_id(self, obj):
        return obj.city.id

    def get_city_name(self, obj):
        return obj.city.name

    def get_vehicle_type_id(self, obj):
        return obj.vehicle_type.id

    def get_name(self, obj):
        # resolved_name annotated by PopularRentalService
        return getattr(obj, "resolved_name", obj.display_name or obj.vehicle_type.name)

    def get_brand(self, obj):
        return obj.vehicle_type.brand.name if obj.vehicle_type.brand else None

    def get_vehicle_type_category(self, obj):
        return obj.vehicle_type.vehicle_type

    def get_fuel_type(self, obj):
        return obj.vehicle_type.fuel_type

    def get_transmission_type(self, obj):
        return obj.vehicle_type.transmission_type

    def get_seats(self, obj):
        return obj.vehicle_type.seats

    def get_image_url(self, obj) -> str | None:
        image = getattr(obj, "resolved_image", None)
        if not image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(image.url) if request else image.url

    def get_pickup_location_id(self, obj) -> int | None:
        loc = getattr(obj, "resolved_pickup_location", None)
        return loc.id if loc else None

    def get_pickup_location_name(self, obj) -> str | None:
        loc = getattr(obj, "resolved_pickup_location", None)
        return loc.name if loc else None


class AnnouncementBannerQuerySerializer(serializers.Serializer):
    page = serializers.ChoiceField(choices=["search_result", "vehicle_detail", "home"])


class AnnouncementBannerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    content = serializers.CharField()
    page = serializers.CharField()
    is_current = serializers.BooleanField()


class LegalDocumentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    doc_type = serializers.CharField()
    version = serializers.IntegerField()
    content = serializers.CharField()
    published_at = serializers.DateTimeField(allow_null=True)


class AdminTaxRateSerializer(serializers.ModelSerializer):
    context_label = serializers.CharField(source="get_context_display", read_only=True)

    class Meta:
        model = TaxRate
        fields = [
            "id",
            "context",
            "context_label",
            "name",
            "percentage",
            "cgst_percentage",
            "sgst_percentage",
            "igst_percentage",
            "hsn_sac_code",
            "is_current",
            "version",
            "effective_from",
            "created_at",
        ]
        read_only_fields = ["version"]


class AdminPlatformConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformConfig
        fields = ["id", "key", "value", "description", "data_type"]


class AdminOfferSerializer(serializers.ModelSerializer):
    icon_type_label = serializers.CharField(
        source="get_icon_type_display", read_only=True
    )

    class Meta:
        model = Offer
        fields = [
            "id",
            "title",
            "description",
            "icon_type",
            "icon_type_label",
            "coupon_code",
            "discount_amount",
            "min_order_amount",
            "valid_from",
            "valid_until",
            "is_active",
            "sort_order",
        ]


class AdminPopularRentalSerializer(serializers.ModelSerializer):
    city_name = serializers.CharField(source="city.name", read_only=True)
    vehicle_type_name = serializers.SerializerMethodField()
    pickup_location_name = serializers.CharField(
        source="pickup_location.name", read_only=True, allow_null=True
    )

    class Meta:
        model = PopularRental
        fields = [
            "id",
            "city",
            "city_name",
            "pickup_location",
            "pickup_location_name",
            "vehicle_type",
            "vehicle_type_name",
            "display_name",
            "display_price",
            "display_image",
            "tag",
            "sort_order",
        ]

    def get_vehicle_type_name(self, obj):
        return f"{obj.vehicle_type.brand.name} {obj.vehicle_type.name}"


class AdminAnnouncementBannerSerializer(serializers.ModelSerializer):
    page_label = serializers.CharField(source="get_page_display", read_only=True)

    class Meta:
        model = AnnouncementBanner
        fields = ["id", "content", "page", "page_label", "is_current", "is_active"]


class AdminCancellationTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = CancellationTier
        fields = [
            "id",
            "payment_mode",
            "min_hours_before_pickup",
            "max_hours_before_pickup",
            "refund_percentage",
            "label",
            "description",
        ]


class AdminCancellationPolicyListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CancellationPolicy
        fields = ["id", "name", "is_current", "refund_note", "version", "created_at"]


class AdminCancellationPolicyDetailSerializer(serializers.ModelSerializer):
    tiers = AdminCancellationTierSerializer(many=True, read_only=True)

    class Meta:
        model = CancellationPolicy
        fields = [
            "id",
            "name",
            "is_current",
            "refund_note",
            "version",
            "created_at",
            "tiers",
        ]


class AdminCancellationPolicyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    refund_note = serializers.CharField(max_length=300)
    is_current = serializers.BooleanField(default=True)
    tiers = AdminCancellationTierSerializer(many=True)

    def validate_tiers(self, tiers):
        """
        Mirrors CancellationTierInlineFormSet.clean() from Django
        Admin — needed because CancellationTier.clean() alone only
        checks a tier against rows ALREADY in the database, which is
        empty for a brand-new policy version. Without this, two
        overlapping tiers submitted together would sail through.
        """
        if not tiers:
            raise serializers.ValidationError("At least one tier is required.")

        by_mode: dict[str, list[tuple[int, int | None]]] = {}
        for tier in tiers:
            lo = tier["min_hours_before_pickup"]
            hi = tier.get("max_hours_before_pickup")
            if hi is not None and hi <= lo:
                raise serializers.ValidationError(
                    f"max_hours_before_pickup ({hi}) must be greater than min_hours_before_pickup ({lo})."
                )
            by_mode.setdefault(tier["payment_mode"], []).append((lo, hi))

        for mode, ranges in by_mode.items():
            ranges.sort(key=lambda r: r[0])
            for i in range(len(ranges) - 1):
                lo, hi = ranges[i]
                next_lo, _ = ranges[i + 1]
                if hi is None or next_lo < hi:
                    raise serializers.ValidationError(
                        f"Overlapping {mode} tiers: {lo}\u2013{hi if hi is not None else '\u221e'} hrs overlaps the tier starting at {next_lo} hrs."
                    )
        return tiers


class AdminLegalDocumentSerializer(serializers.ModelSerializer):
    doc_type_label = serializers.CharField(
        source="get_doc_type_display", read_only=True
    )
    published_by_name = serializers.SerializerMethodField()

    class Meta:
        model = LegalDocument
        fields = [
            "id",
            "doc_type",
            "doc_type_label",
            "version",
            "content",
            "is_current",
            "published_at",
            "published_by_name",
            "created_at",
        ]
        read_only_fields = ["version", "published_at"]

    def get_published_by_name(self, obj):
        return obj.published_by.get_full_name() if obj.published_by else None


class AdminLegalDocumentCreateSerializer(serializers.Serializer):
    doc_type = serializers.ChoiceField(choices=LegalDocument.DocType.choices)
    content = serializers.CharField()
    is_current = serializers.BooleanField(default=True)


class AdminDashboardSerializer(serializers.Serializer):
    pending_vendor_approvals = serializers.IntegerField()
    pending_listing_approvals = serializers.IntegerField()
    revenue_this_month = serializers.DecimalField(max_digits=14, decimal_places=2)
    revenue_last_month = serializers.DecimalField(max_digits=14, decimal_places=2)
    revenue_trend_pct = serializers.FloatField()
    bookings_this_month = serializers.IntegerField()
    bookings_last_month = serializers.IntegerField()
    bookings_trend_pct = serializers.FloatField()
    weekly_booking_bars = serializers.ListField(child=serializers.IntegerField())
    active_vendors = serializers.IntegerField()
    vendors_this_month = serializers.IntegerField()
    vendors_last_month = serializers.IntegerField()
    vendors_trend_pct = serializers.FloatField()
    total_customers = serializers.IntegerField()
    booking_status_counts = serializers.DictField(child=serializers.IntegerField())
    pending_payout_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending_payout_count = serializers.IntegerField()
    recent_bookings = AdminBookingListSerializer(many=True)
    range_label = serializers.CharField()
