from rest_framework import serializers

# ── Cancellation Policy ───────────────────────────────────────────────


class CancellationTierSerializer(serializers.Serializer):
    hours_before_pickup = serializers.IntegerField()
    refund_percentage = serializers.IntegerField()
    label = serializers.CharField()
    description = serializers.CharField()


class CancellationPolicySerializer(serializers.Serializer):
    rules = CancellationTierSerializer(many=True)
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
        return obj.vehicle_type.brand

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
