# apps/vendors/serializers.py
from rest_framework import serializers
from apps.bookings.serializers import VendorBookingListSerializer


class VendorTermsSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()
    version = serializers.IntegerField()
    terms_items = serializers.ListField(child=serializers.CharField(), default=list)
    security_deposit_note = serializers.CharField(allow_blank=True)
    operating_hours_note = serializers.CharField(allow_blank=True)
    distance_limit_note = serializers.CharField(allow_blank=True)
    excess_charge_note = serializers.CharField(allow_blank=True)
    late_penalty_note = serializers.CharField(allow_blank=True)


class VendorTermsUpdateSerializer(serializers.Serializer):
    terms_items = serializers.ListField(
        child=serializers.CharField(allow_blank=False), required=False, default=list
    )
    security_deposit_note = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    operating_hours_note = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    distance_limit_note = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    excess_charge_note = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    late_penalty_note = serializers.CharField(
        required=False, allow_blank=True, default=""
    )


class VendorDashboardSerializer(serializers.Serializer):
    vendor_status = serializers.CharField()
    vendor_status_label = serializers.CharField()
    vendor_rejection_reason = serializers.CharField(allow_blank=True)
    current_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_this_month = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_last_month = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_trend_pct = serializers.FloatField()
    orders_this_month = serializers.IntegerField()
    orders_last_month = serializers.IntegerField()
    orders_trend_pct = serializers.FloatField()
    weekly_order_bars = serializers.ListField(child=serializers.IntegerField())
    range_label = serializers.CharField()
    # Reuses the exact serializer the Bookings list/detail screens
    # already use — same fields, same available_next_statuses for
    # quick-action buttons, so the frontend can reuse BookingListItem
    # directly instead of a new component.
    bookings_to_start = VendorBookingListSerializer(many=True)
    bookings_to_return = VendorBookingListSerializer(many=True)
    fleet_total_listings = serializers.IntegerField()
    fleet_pending_approval = serializers.IntegerField()
    fleet_blocked_units = serializers.IntegerField()
    recent_bookings = VendorBookingListSerializer(many=True)
