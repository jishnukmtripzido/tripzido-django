from rest_framework import serializers
from apps.payments.models import VendorPayout, VendorPayoutItem, Payment


class VendorPayoutListSerializer(serializers.ModelSerializer):
    """One card per payout, for the vendor's Ledger list screen."""

    status_label = serializers.CharField(source="get_status_display")
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = VendorPayout
        fields = [
            "id",
            "status",
            "status_label",
            "total_amount",
            "items_count",
            "period_start",
            "period_end",
            "utr_number",
            "paid_at",
            "created_at",
        ]

    def get_items_count(self, payout):
        # .count() rather than len(payout.items.all()) — this
        # serializer is used on the list endpoint, which doesn't
        # prefetch items (only the detail endpoint does), so a plain
        # count query here is correct and avoids fetching rows we'd
        # never use anyway.
        return payout.items.count()


class VendorPayoutItemDetailSerializer(serializers.ModelSerializer):
    booking_reference = serializers.CharField(source="booking.booking_reference")
    vehicle_name = serializers.CharField(source="booking.listing.vehicle_type.name")
    pickup_date = serializers.DateField(source="booking.pickup_date")
    dropoff_date = serializers.DateField(source="booking.dropoff_date")

    class Meta:
        model = VendorPayoutItem
        fields = [
            "id",
            "booking_id",
            "booking_reference",
            "vehicle_name",
            "pickup_date",
            "dropoff_date",
            "amount",
        ]


class VendorPayoutDetailSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")
    items = VendorPayoutItemDetailSerializer(many=True, read_only=True)

    class Meta:
        model = VendorPayout
        fields = [
            "id",
            "status",
            "status_label",
            "total_amount",
            "period_start",
            "period_end",
            "bank_account_snapshot",
            "utr_number",
            "paid_at",
            "note",
            "items",
            "created_at",
        ]


class AdminPaymentSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payment_type_label = serializers.CharField(
        source="get_payment_type_display", read_only=True
    )
    booking_reference = serializers.CharField(
        source="booking.booking_reference", read_only=True
    )
    vendor_name = serializers.CharField(
        source="booking.listing.vendor.business_name", read_only=True
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "booking",
            "booking_reference",
            "vendor_name",
            "payment_type",
            "payment_type_label",
            "amount",
            "gateway",
            "gateway_order_id",
            "gateway_payment_id",
            "status",
            "status_label",
            "attempt_number",
            "initiated_at",
            "completed_at",
            "failed_at",
            "failure_reason",
            "webhook_received_at",
            "is_reconciled",
        ]


class AdminEligibleBookingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    booking_reference = serializers.CharField()
    vendor_id = serializers.IntegerField(source="listing.vendor_id")
    vendor_name = serializers.CharField(source="listing.vendor.business_name")
    vehicle_name = serializers.SerializerMethodField()
    dropoff_date = serializers.DateField()
    net_amount = serializers.DecimalField(max_digits=12, decimal_places=2)

    def get_vehicle_name(self, obj):
        vt = obj.listing.vehicle_type
        return f"{vt.brand.name} {vt.name}"


class AdminVendorPayoutItemSerializer(serializers.ModelSerializer):
    booking_reference = serializers.CharField(source="booking.booking_reference")
    vehicle_name = serializers.SerializerMethodField()
    pickup_date = serializers.DateField(source="booking.pickup_date")
    dropoff_date = serializers.DateField(source="booking.dropoff_date")

    class Meta:
        model = VendorPayoutItem
        fields = [
            "id",
            "booking_id",
            "booking_reference",
            "vehicle_name",
            "pickup_date",
            "dropoff_date",
            "amount",
        ]

    def get_vehicle_name(self, obj):
        vt = obj.booking.listing.vehicle_type
        return f"{vt.brand.name} {vt.name}"


class AdminVendorPayoutListSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.business_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = VendorPayout
        fields = [
            "id",
            "vendor",
            "vendor_name",
            "status",
            "status_label",
            "total_amount",
            "items_count",
            "period_start",
            "period_end",
            "utr_number",
            "paid_at",
            "created_at",
        ]

    def get_items_count(self, obj):
        return obj.items.count()


class AdminVendorPayoutDetailSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.business_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    paid_by_name = serializers.SerializerMethodField()
    items = AdminVendorPayoutItemSerializer(many=True, read_only=True)

    class Meta:
        model = VendorPayout
        fields = [
            "id",
            "vendor",
            "vendor_name",
            "status",
            "status_label",
            "total_amount",
            "period_start",
            "period_end",
            "bank_account_snapshot",
            "utr_number",
            "paid_at",
            "paid_by_name",
            "note",
            "items",
            "created_at",
        ]

    def get_paid_by_name(self, obj):
        return obj.paid_by.get_full_name() if obj.paid_by else None


class AdminVendorPayoutCreateSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()
    booking_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False
    )
    period_start = serializers.DateField(required=False, allow_null=True)
    period_end = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class AdminVendorPayoutStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=VendorPayout.Status.choices)
    utr_number = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")
