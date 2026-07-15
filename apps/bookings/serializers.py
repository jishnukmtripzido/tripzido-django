# apps/bookings/serializers.py

from rest_framework import serializers
from apps.bookings.models import Booking, BookingCancellation
from apps.payments.models import Payment

# ── List view (BookingsList.tsx card) ──────────────────────────────────


class BookingListSerializer(serializers.ModelSerializer):
    """
    One card per booking, shaped to match the hardcoded `bookings` array
    in BookingsList.tsx (id, vehicle, bookingDate, location, startDate,
    endDate, duration, paid, deposit, image) plus a few extra fields the
    "View Details" link needs.
    """

    vehicle = serializers.CharField(source="listing.vehicle_type.name")
    image = serializers.SerializerMethodField()
    location = serializers.CharField(source="pickup_location.name")
    booking_date = serializers.DateTimeField(source="created_at")
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    paid = serializers.SerializerMethodField()
    deposit = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display")

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_reference",
            "vehicle",
            "image",
            "location",
            "booking_date",
            "start_date",
            "end_date",
            "duration",
            "paid",
            "deposit",
            "status",
            "status_label",
        ]

    def get_image(self, booking):
        request = self.context.get("request")
        image = booking.listing.vehicle_type.primary_image
        if not image:
            return None
        return request.build_absolute_uri(image.url) if request else image.url

    def get_start_date(self, booking):
        from datetime import datetime

        return datetime.combine(booking.pickup_date, booking.pickup_time).isoformat()

    def get_end_date(self, booking):
        from datetime import datetime

        return datetime.combine(booking.dropoff_date, booking.dropoff_time).isoformat()

    def get_duration(self, booking):
        from apps.vehicles.utils import format_duration
        from datetime import datetime

        pickup = datetime.combine(booking.pickup_date, booking.pickup_time)
        dropoff = datetime.combine(booking.dropoff_date, booking.dropoff_time)
        hours = (dropoff - pickup).total_seconds() / 3600
        return format_duration(hours)

    def get_paid(self, booking):
        # "Paid" on the card = whatever's actually been collected so
        # far, not the full rent — that's advance_amount for
        # PENDING_PAYMENT/CONFIRMED bookings still owing a balance, and
        # the full amount once nothing remains.
        return float(booking.advance_amount)

    def get_deposit(self, booking):
        return float(booking.security_deposit_amount)


# ── Cancellation ──────────────────────────────────────────────────────


class CancelBookingRequestSerializer(serializers.Serializer):
    """
    Request body for POST /api/bookings/{id}/cancel/. Reason codes are
    restricted to BookingCancellation.CUSTOMER_REASON_CODES — vendor/
    admin-only reasons (e.g. VENDOR_BREAKDOWN) aren't valid here since
    this endpoint is only ever called by the booking's own customer.
    """

    reason_code = serializers.ChoiceField(
        choices=BookingCancellation.CUSTOMER_REASON_CODES
    )
    reason_text = serializers.CharField(
        required=False, allow_blank=True, max_length=1000
    )

    def validate(self, attrs):
        is_other = attrs["reason_code"] == BookingCancellation.CancellationReason.OTHER
        if is_other and not attrs.get("reason_text", "").strip():
            raise serializers.ValidationError(
                {"reason_text": "Please tell us a bit more when selecting 'Other'."}
            )
        return attrs


class CancellationPolicyRuleSerializer(serializers.Serializer):
    """
    One row of the full refund schedule, as shaped by
    apps.administrations.services.CancellationPolicyService.get_current_policy().
    """

    hours_before_pickup = serializers.IntegerField()
    refund_percentage = serializers.FloatField()
    label = serializers.CharField()
    description = serializers.CharField()


class CancellationPreviewSerializer(serializers.Serializer):
    """
    Response shape for GET /api/bookings/{id}/cancellation-preview/.
    Matches the dict returned by CancellationService.preview_cancellation().
    """

    payment_mode = serializers.CharField()
    hours_before_pickup = serializers.FloatField()
    refund_percentage = serializers.FloatField()
    paid_amount = serializers.FloatField()
    refundable_amount = serializers.FloatField()
    forfeited_amount = serializers.FloatField()
    policy_rules = serializers.SerializerMethodField()
    policy_note = serializers.CharField(allow_blank=True)

    def get_policy_rules(self, obj):
        rules_key = (
            "full_payment_rules"
            if obj["payment_mode"] == Booking.PaymentMode.FULL
            else "partial_payment_rules"
        )
        return obj[rules_key]


class BookingCancellationSerializer(serializers.ModelSerializer):
    """Response shape after a successful cancellation, and the nested
    `cancellation` field on BookingDetailSerializer once cancelled."""

    reason_label = serializers.CharField(source="get_reason_code_display")

    class Meta:
        model = BookingCancellation
        fields = [
            "id",
            "booking_id",
            "reason_code",
            "reason_label",
            "reason_text",
            "hours_before_pickup_at_cancellation",
            "refund_percentage",
            "refundable_amount",
            "forfeited_amount",
            "created_at",
        ]


# ── Detail view ─────────────────────────────────────────────────────────


class BookingPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "payment_type",
            "amount",
            "status",
            "gateway_order_id",
            "gateway_payment_id",
            "initiated_at",
            "completed_at",
            "failed_at",
            "failure_reason",
        ]


class BookingDetailSerializer(serializers.ModelSerializer):
    """
    Full booking detail for the "View Details" page — vehicle, vendor,
    location, pricing snapshot, cancellation/handover state, and payment
    history.
    """

    vehicle_name = serializers.CharField(source="listing.vehicle_type.name")
    vehicle_image = serializers.SerializerMethodField()
    transmission_type = serializers.CharField(
        source="listing.vehicle_type.transmission_type"
    )
    fuel_type = serializers.CharField(source="listing.vehicle_type.fuel_type")

    vendor_name = serializers.CharField(source="listing.vendor.business_name")

    pickup_location_name = serializers.CharField(source="pickup_location.name")
    pickup_location_address = serializers.SerializerMethodField()

    package_name = serializers.CharField(
        source="pricing_package.package_type.name", allow_null=True
    )

    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()

    status_label = serializers.CharField(source="get_status_display")
    payment_mode_label = serializers.CharField(source="get_payment_mode_display")

    # Was: payments = BookingPaymentSerializer(many=True, read_only=True)
    # That used the reverse `booking.payments` accessor, which only
    # returns rows whose Payment.booking FK points at THIS exact
    # Booking row. A bulk booking (quantity > 1 at checkout) creates N
    # Booking rows sharing one booking_group_id, but the single shared
    # Payment is only ever attached to bookings[0] — so every other
    # booking in the group silently showed "No payments recorded yet."
    # Querying by booking_group_id instead fixes that for every member
    # of the group, not just the first one.
    payments = serializers.SerializerMethodField()

    can_cancel = serializers.SerializerMethodField()
    cancellation = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_reference",
            "vehicle_name",
            "vehicle_image",
            "transmission_type",
            "fuel_type",
            "vendor_name",
            "pickup_location_name",
            "pickup_location_address",
            "package_name",
            "start_date",
            "end_date",
            "duration",
            "status",
            "status_label",
            "payment_mode",
            "payment_mode_label",
            "listing_amount",
            "advance_amount",
            "remaining_amount",
            "security_deposit_amount",
            "handed_over_at",
            "returned_at",
            "cancelled_at",
            "cancelled_by_role",
            "payments",
            "can_cancel",
            "cancellation",
            "created_at",
        ]

    def get_vehicle_image(self, booking):
        request = self.context.get("request")
        image = booking.listing.vehicle_type.primary_image
        if not image:
            return None
        return request.build_absolute_uri(image.url) if request else image.url

    def get_pickup_location_address(self, booking):
        # Exact address only revealed post-booking, mirroring the
        # `exact_address_revealed_after_booking` flag in
        # VehiclePickupLocationSerializer on the vehicles side — a
        # CONFIRMED+ booking has earned that reveal.
        return getattr(booking.pickup_location, "address", None)

    def get_start_date(self, booking):
        from datetime import datetime

        return datetime.combine(booking.pickup_date, booking.pickup_time).isoformat()

    def get_end_date(self, booking):
        from datetime import datetime

        return datetime.combine(booking.dropoff_date, booking.dropoff_time).isoformat()

    def get_duration(self, booking):
        from apps.vehicles.utils import format_duration
        from datetime import datetime

        pickup = datetime.combine(booking.pickup_date, booking.pickup_time)
        dropoff = datetime.combine(booking.dropoff_date, booking.dropoff_time)
        hours = (dropoff - pickup).total_seconds() / 3600
        return format_duration(hours)

    def get_payments(self, booking):
        payments = Payment.objects.filter(
            booking_group_id=booking.booking_group_id
        ).order_by("-initiated_at")
        return BookingPaymentSerializer(payments, many=True).data

    def get_can_cancel(self, booking) -> bool:
        # Mirrors CancellationService.CANCELLABLE_STATUSES — kept as a
        # literal status check here (rather than importing the service)
        # to avoid a serializers → services import cycle. Keep these in
        # sync if the cancellable-status rule ever changes.
        return booking.status == Booking.Status.CONFIRMED

    def get_cancellation(self, booking):
        cancellation = getattr(booking, "cancellation", None)
        if cancellation is None:
            return None
        return BookingCancellationSerializer(cancellation).data


# ── Confirmation view (post-checkout) ───────────────────────────────────


class BookingConfirmationItemSerializer(serializers.ModelSerializer):
    """
    One vehicle's booking within a confirmation group. A bulk booking
    (quantity > 1 at checkout) creates one of these per vehicle, all
    sharing the same booking_group_id — see BookingConfirmationSerializer.
    """

    vehicle_name = serializers.CharField(source="listing.vehicle_type.name")
    vehicle_image = serializers.SerializerMethodField()
    transmission_type = serializers.CharField(
        source="listing.vehicle_type.transmission_type"
    )
    fuel_type = serializers.CharField(source="listing.vehicle_type.fuel_type")
    vendor_name = serializers.CharField(source="listing.vendor.business_name")
    pickup_location_name = serializers.CharField(source="pickup_location.name")
    package_name = serializers.CharField(
        source="pricing_package.package_type.name", allow_null=True
    )
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display")

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_reference",
            "vehicle_name",
            "vehicle_image",
            "transmission_type",
            "fuel_type",
            "vendor_name",
            "pickup_location_name",
            "package_name",
            "start_date",
            "end_date",
            "duration",
            "status",
            "status_label",
            "listing_amount",
            "advance_amount",
            "remaining_amount",
            "security_deposit_amount",
        ]

    def get_vehicle_image(self, booking):
        request = self.context.get("request")
        image = booking.listing.vehicle_type.primary_image
        if not image:
            return None
        return request.build_absolute_uri(image.url) if request else image.url

    def get_start_date(self, booking):
        from datetime import datetime

        return datetime.combine(booking.pickup_date, booking.pickup_time).isoformat()

    def get_end_date(self, booking):
        from datetime import datetime

        return datetime.combine(booking.dropoff_date, booking.dropoff_time).isoformat()

    def get_duration(self, booking):
        from apps.vehicles.utils import format_duration
        from datetime import datetime

        pickup = datetime.combine(booking.pickup_date, booking.pickup_time)
        dropoff = datetime.combine(booking.dropoff_date, booking.dropoff_time)
        hours = (dropoff - pickup).total_seconds() / 3600
        return format_duration(hours)


class BookingConfirmationSerializer(serializers.Serializer):
    """
    Response shape for GET /api/bookings/confirmation/?group=<uuid>.

    Deliberately keyed by booking_group_id, not booking_reference — one
    checkout can create several Booking rows (one per vehicle) sharing a
    single group id and a single Payment, so the confirmation page needs
    the whole group, not one row.

    Expects a plain dict built by the view (see BookingConfirmationView):
        {
            "booking_group_id": str(uuid),
            "payment_status": str,
            "payment_mode": "FULL" | "PARTIAL" | "PAY_AT_PICKUP",
            "total_paid": float,
            "total_deposit": float,
            "vehicle_count": int,
            "bookings": <queryset or list of Booking instances>,
        }
    """

    booking_group_id = serializers.UUIDField()
    payment_status = serializers.CharField(allow_blank=True)
    payment_mode = serializers.CharField()
    total_paid = serializers.FloatField()
    total_deposit = serializers.FloatField()
    vehicle_count = serializers.IntegerField()
    bookings = BookingConfirmationItemSerializer(many=True)
