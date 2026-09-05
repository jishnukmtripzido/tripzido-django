# apps/bookings/serializers.py

from rest_framework import serializers
from apps.bookings.models import Booking, BookingCancellation
from apps.payments.models import Payment
from apps.vendors.models import VendorTerms
from apps.vehicles.models import ReviewRating
from django.utils import timezone

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

        return timezone.make_aware(
            datetime.combine(booking.pickup_date, booking.pickup_time)
        ).isoformat()

    def get_end_date(self, booking):
        from datetime import datetime

        return timezone.make_aware(
            datetime.combine(booking.dropoff_date, booking.dropoff_time)
        ).isoformat()

    def get_duration(self, booking):
        from apps.vehicles.utils import format_duration
        from datetime import datetime

        pickup = timezone.make_aware(
            datetime.combine(booking.pickup_date, booking.pickup_time)
        )
        dropoff = timezone.make_aware(
            datetime.combine(booking.dropoff_date, booking.dropoff_time)
        )
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
    vendor_terms = serializers.SerializerMethodField()
    things_to_remember = serializers.SerializerMethodField()
    pickup_point = serializers.SerializerMethodField()

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
    verification_pin = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_reference",
            "vehicle_name",
            "verification_pin",
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
            "vendor_terms",
            "things_to_remember",
            "pickup_point",
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

        return timezone.make_aware(
            datetime.combine(booking.pickup_date, booking.pickup_time)
        ).isoformat()

    def get_end_date(self, booking):
        from datetime import datetime

        return timezone.make_aware(
            datetime.combine(booking.dropoff_date, booking.dropoff_time)
        ).isoformat()

    def get_duration(self, booking):
        from apps.vehicles.utils import format_duration
        from datetime import datetime

        pickup = timezone.make_aware(
            datetime.combine(booking.pickup_date, booking.pickup_time)
        )
        dropoff = timezone.make_aware(
            datetime.combine(booking.dropoff_date, booking.dropoff_time)
        )
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

    def get_vendor_terms(self, booking):
        # Things to Remember + vendor T&C are only meaningful once the
        # booking is actually secured — shown from CONFIRMED onward,
        # same "reveal after commitment" reasoning already used above
        # for pickup_location_address, not while still PENDING_PAYMENT.
        if booking.status not in (
            Booking.Status.CONFIRMED,
            Booking.Status.ONGOING,
            Booking.Status.COMPLETED,
        ):
            return None
        terms = VendorTerms.objects.filter(
            vendor=booking.listing.vendor, is_current=True
        ).first()
        if terms is None:
            return None
        return VendorTermsSerializer(terms).data

    def get_things_to_remember(self, booking):
        # Same gating as vendor_terms/pickup_location_address above —
        # only meaningful once the booking is actually secured.
        if booking.status not in (
            Booking.Status.CONFIRMED,
            Booking.Status.ONGOING,
            Booking.Status.COMPLETED,
        ):
            return None

        from apps.vehicles.services import VehicleDetailService

        listing = booking.listing
        terms = VendorTerms.objects.filter(
            vendor=listing.vendor, is_current=True
        ).first()
        operating_hours = VehicleDetailService._build_operating_hours(listing)
        policies = VehicleDetailService._build_policies(listing, terms, operating_hours)

        # security_deposit uses the BOOKING's own snapshot amount, not
        # the listing's current live value — a confirmed booking
        # should reflect what applied when it was made, even if the
        # vendor has since changed the listing's deposit amount.
        policies["security_deposit"] = float(booking.security_deposit_amount)

        return BookingPoliciesSerializer(policies).data

    def get_pickup_point(self, booking):
        # Not status-gated, unlike vendor_terms/things_to_remember —
        # pickup_location_address above is already shown unconditionally
        # once a booking row exists at all, and this is the same
        # category of "where do I go" information at a more precise
        # level, so it follows that same existing precedent rather
        # than introducing a third different gating rule.
        point = booking.listing.pickup_point
        if point is None:
            return None
        return BookingPickupPointSerializer(point).data

    def get_verification_pin(self, booking):
        # Only meaningful before the trip has started — once ONGOING
        # or beyond, there's nothing left to verify, so it disappears.
        if booking.status != Booking.Status.CONFIRMED:
            return None
        return booking.verification_pin


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

        return timezone.make_aware(
            datetime.combine(booking.pickup_date, booking.pickup_time)
        ).isoformat()

    def get_end_date(self, booking):
        from datetime import datetime

        return timezone.make_aware(
            datetime.combine(booking.dropoff_date, booking.dropoff_time)
        ).isoformat()

    def get_duration(self, booking):
        from apps.vehicles.utils import format_duration
        from datetime import datetime

        pickup = timezone.make_aware(
            datetime.combine(booking.pickup_date, booking.pickup_time)
        )
        dropoff = timezone.make_aware(
            datetime.combine(booking.dropoff_date, booking.dropoff_time)
        )
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


class VendorBookingListSerializer(serializers.ModelSerializer):
    """One card per booking, for the vendor's own Bookings list."""

    vehicle_name = serializers.CharField(source="listing.vehicle_type.name")
    vehicle_image = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.CharField(source="customer.phone_number")
    location_name = serializers.CharField(source="pickup_location.name")
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display")
    available_next_statuses = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_reference",
            "vehicle_name",
            "vehicle_image",
            "customer_name",
            "customer_phone",
            "location_name",
            "start_date",
            "end_date",
            "duration",
            "status",
            "status_label",
            "is_offline",
            "listing_amount",
            "advance_amount",
            "remaining_amount",
            "available_next_statuses",
        ]

    def get_vehicle_image(self, booking):
        request = self.context.get("request")
        image = booking.listing.vehicle_type.primary_image
        if not image:
            return None
        return request.build_absolute_uri(image.url) if request else image.url

    def get_customer_name(self, booking):
        name = f"{booking.customer.first_name} {booking.customer.last_name}".strip()
        return name or booking.customer.phone_number

    def get_start_date(self, booking):
        from datetime import datetime

        return timezone.make_aware(
            datetime.combine(booking.pickup_date, booking.pickup_time)
        ).isoformat()

    def get_end_date(self, booking):
        from datetime import datetime

        return timezone.make_aware(
            datetime.combine(booking.dropoff_date, booking.dropoff_time)
        ).isoformat()

    def get_duration(self, booking):
        from apps.vehicles.utils import format_duration
        from datetime import datetime

        pickup = timezone.make_aware(
            datetime.combine(booking.pickup_date, booking.pickup_time)
        )
        dropoff = timezone.make_aware(
            datetime.combine(booking.dropoff_date, booking.dropoff_time)
        )
        hours = (dropoff - pickup).total_seconds() / 3600
        return format_duration(hours)

    def get_available_next_statuses(self, booking):
        from apps.bookings.services import VendorBookingService

        return VendorBookingService.ALLOWED_TRANSITIONS.get(booking.status, [])


class VendorBookingDetailSerializer(serializers.ModelSerializer):
    """Full detail for the vendor's booking detail page."""

    vehicle_name = serializers.CharField(source="listing.vehicle_type.name")
    vehicle_image = serializers.SerializerMethodField()
    transmission_type = serializers.CharField(
        source="listing.vehicle_type.transmission_type"
    )
    fuel_type = serializers.CharField(source="listing.vehicle_type.fuel_type")
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.CharField(source="customer.phone_number")
    pickup_location_name = serializers.CharField(source="pickup_location.name")
    pickup_location_address = serializers.CharField(source="pickup_location.address")
    package_name = serializers.CharField(
        source="pricing_package.package_type.name", allow_null=True
    )
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display")
    payment_mode_label = serializers.CharField(source="get_payment_mode_display")
    payments = serializers.SerializerMethodField()
    cancellation = serializers.SerializerMethodField()
    available_next_statuses = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_reference",
            "is_offline",
            "vehicle_name",
            "vehicle_image",
            "transmission_type",
            "fuel_type",
            "customer_name",
            "customer_phone",
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
            "cancellation",
            "available_next_statuses",
            "created_at",
        ]

    def get_vehicle_image(self, booking):
        request = self.context.get("request")
        image = booking.listing.vehicle_type.primary_image
        if not image:
            return None
        return request.build_absolute_uri(image.url) if request else image.url

    def get_customer_name(self, booking):
        name = f"{booking.customer.first_name} {booking.customer.last_name}".strip()
        return name or booking.customer.phone_number

    def get_start_date(self, booking):
        from datetime import datetime

        return timezone.make_aware(
            datetime.combine(booking.pickup_date, booking.pickup_time)
        ).isoformat()

    def get_end_date(self, booking):
        from datetime import datetime

        return timezone.make_aware(
            datetime.combine(booking.dropoff_date, booking.dropoff_time)
        ).isoformat()

    def get_duration(self, booking):
        from apps.vehicles.utils import format_duration
        from datetime import datetime

        pickup = timezone.make_aware(
            datetime.combine(booking.pickup_date, booking.pickup_time)
        )
        dropoff = timezone.make_aware(
            datetime.combine(booking.dropoff_date, booking.dropoff_time)
        )
        hours = (dropoff - pickup).total_seconds() / 3600
        return format_duration(hours)

    def get_payments(self, booking):
        payments = Payment.objects.filter(
            booking_group_id=booking.booking_group_id
        ).order_by("-initiated_at")
        return BookingPaymentSerializer(payments, many=True).data

    def get_cancellation(self, booking):
        cancellation = getattr(booking, "cancellation", None)
        if cancellation is None:
            return None
        return BookingCancellationSerializer(cancellation).data

    def get_available_next_statuses(self, booking):
        from apps.bookings.services import VendorBookingService

        return VendorBookingService.ALLOWED_TRANSITIONS.get(booking.status, [])


class VendorBookingStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Booking.Status.choices)
    verification_pin = serializers.CharField(
        required=False, allow_blank=True, default=""
    )


class VendorCancelBookingRequestSerializer(serializers.Serializer):
    reason_code = serializers.ChoiceField(
        choices=BookingCancellation.VENDOR_REASON_CODES
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


class AdminCancelBookingRequestSerializer(serializers.Serializer):
    reason_text = serializers.CharField(max_length=1000)
    refund_percentage_override = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, min_value=0, max_value=100
    )


class AdminBookingListSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(
        source="listing.vendor.business_name", read_only=True
    )
    customer_name = serializers.SerializerMethodField()
    vehicle_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payment_mode_label = serializers.CharField(
        source="get_payment_mode_display", read_only=True
    )

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_reference",
            "vendor_name",
            "customer_name",
            "vehicle_name",
            "pickup_date",
            "dropoff_date",
            "status",
            "status_label",
            "payment_mode",
            "payment_mode_label",
            "is_offline",
            "net_amount",
            "created_at",
        ]

    def get_customer_name(self, obj):
        return (
            f"{obj.customer.first_name} {obj.customer.last_name or ''}".strip()
            or obj.customer.phone_number
        )

    def get_vehicle_name(self, obj):
        vt = obj.listing.vehicle_type
        return f"{vt.brand.name} {vt.name}"


class AdminPaymentSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    payment_type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    status = serializers.CharField()
    gateway_order_id = serializers.CharField()
    initiated_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)


class AdminBookingCancellationSerializer(serializers.Serializer):
    reason_code = serializers.CharField()
    reason_text = serializers.CharField(allow_blank=True)
    cancelled_by_role = serializers.CharField()
    hours_before_pickup_at_cancellation = serializers.DecimalField(
        max_digits=8, decimal_places=2, allow_null=True
    )
    refund_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    refundable_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    forfeited_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    created_at = serializers.DateTimeField()


class AdminBookingDetailSerializer(serializers.ModelSerializer):
    vendor_id = serializers.IntegerField(source="listing.vendor_id", read_only=True)
    vendor_name = serializers.CharField(
        source="listing.vendor.business_name", read_only=True
    )
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.CharField(
        source="customer.phone_number", read_only=True
    )
    vehicle_name = serializers.SerializerMethodField()
    pickup_location_name = serializers.CharField(
        source="pickup_location.name", read_only=True
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payment_mode_label = serializers.CharField(
        source="get_payment_mode_display", read_only=True
    )
    payments = AdminPaymentSummarySerializer(many=True, read_only=True)
    cancellation = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_reference",
            "booking_group_id",
            "vendor_id",
            "vendor_name",
            "customer_name",
            "customer_phone",
            "vehicle_name",
            "pickup_location_name",
            "pickup_date",
            "pickup_time",
            "dropoff_date",
            "dropoff_time",
            "status",
            "status_label",
            "payment_mode",
            "payment_mode_label",
            "is_offline",
            "listing_amount",
            "commission_amount",
            "net_commission_amount",
            "net_amount",
            "advance_amount",
            "remaining_amount",
            "security_deposit_amount",
            "vendor_tax_percentage",
            "vendor_tax_amount",
            "commission_tax_percentage",
            "commission_tax_amount",
            "handed_over_at",
            "returned_at",
            "cancelled_at",
            "cancelled_by_role",
            "payments",
            "cancellation",
            "created_at",
        ]

    def get_customer_name(self, obj):
        return (
            f"{obj.customer.first_name} {obj.customer.last_name or ''}".strip()
            or obj.customer.phone_number
        )

    def get_vehicle_name(self, obj):
        vt = obj.listing.vehicle_type
        return f"{vt.brand.name} {vt.name}"

    def get_cancellation(self, obj):
        # Accessing obj.cancellation directly on a booking with no
        # cancellation record raises RelatedObjectDoesNotExist rather
        # than returning None — this getattr guard is what actually
        # makes the field nullable.
        cancellation = getattr(obj, "cancellation", None)
        if cancellation is None:
            return None
        return AdminBookingCancellationSerializer(cancellation).data


class VendorTermsSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorTerms
        fields = [
            "terms_items",
            "security_deposit_note",
            "operating_hours_note",
            "distance_limit_note",
            "excess_charge_note",
            "late_penalty_note",
        ]


class BookingPoliciesSerializer(serializers.Serializer):
    """
    Same "Things to Remember" shape as VehiclePoliciesSerializer on the
    vehicle-detail page (apps.vehicles) — field names match 1:1 so the
    frontend can reuse identical rendering logic. Built via that page's
    own VehicleDetailService methods rather than re-implemented here,
    so the two views can't drift out of sync from hand-copied logic.
    """

    security_deposit = serializers.FloatField()
    distance_limit = serializers.CharField()
    late_penalty_per_hour = serializers.FloatField()
    location_timings = serializers.CharField()
    excess_charge = serializers.CharField()


class BookingPickupPointSerializer(serializers.Serializer):
    label = serializers.CharField(allow_blank=True)
    address = serializers.CharField()
    contact_numbers = serializers.ListField(child=serializers.CharField())
    # Explicit FloatField, not letting ModelSerializer auto-generate a
    # DecimalField for these — DRF's auto DecimalField serializes to a
    # STRING by default (to preserve precision), which caused a real
    # ".toFixed is not a function" crash earlier in this same project
    # when the frontend expected a number. FloatField sidesteps that
    # entirely by outputting a genuine JSON number.
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    google_maps_link = serializers.CharField(allow_blank=True)


# ── Reviews ──────────────────────────────────────────────────────────


class ReviewRatingInputSerializer(serializers.Serializer):
    criterion = serializers.ChoiceField(choices=ReviewRating.Criterion.choices)
    score = serializers.IntegerField(min_value=1, max_value=5)


class BookingReviewSubmitSerializer(serializers.Serializer):
    review_text = serializers.CharField(required=False, allow_blank=True, default="")
    ratings = ReviewRatingInputSerializer(many=True)

    def validate_ratings(self, value):
        if not value:
            raise serializers.ValidationError("Provide at least one rating.")
        criteria = [r["criterion"] for r in value]
        if len(criteria) != len(set(criteria)):
            raise serializers.ValidationError("Duplicate criterion in ratings.")
        return value


class BookingReviewDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    review_text = serializers.CharField(allow_blank=True)
    moderation_status = serializers.CharField()
    created_at = serializers.DateTimeField()
    ratings = serializers.SerializerMethodField()

    def get_ratings(self, review):
        return [
            {
                "criterion": r.criterion,
                "criterion_label": r.get_criterion_display(),
                "score": r.score,
            }
            for r in review.ratings.all()
        ]
