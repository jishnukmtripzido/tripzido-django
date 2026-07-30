from rest_framework import serializers
from apps.payments.models import VendorPayout, VendorPayoutItem


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
