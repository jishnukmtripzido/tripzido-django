# apps/bookings/serializers.py

from rest_framework import serializers
from apps.bookings.models import Booking
from apps.payments.models import Payment
from apps.bookings.models import Booking
from apps.bookings.repositories import BookingRepository

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

    payments = BookingPaymentSerializer(many=True, read_only=True)

    can_cancel = serializers.SerializerMethodField()

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
            "platform_tc_version",
            "handed_over_at",
            "returned_at",
            "cancelled_at",
            "cancelled_by_role",
            "payments",
            "can_cancel",
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

    def get_can_cancel(self, booking) -> bool:
        return booking.status in (
            Booking.Status.PENDING_PAYMENT,
            Booking.Status.CONFIRMED,
        )


class BookingQueryService:

    # Maps the frontend tab name to the Booking.Status values it covers.
    # "cancelled" is intentionally broader than just CANCELLED — from the
    # customer's point of view, payment-failed and expired-unpaid bookings
    # are all "didn't happen" outcomes that belong in the same bucket.
    TAB_STATUS_MAP: dict[str, list[str]] = {
        "pending": [Booking.Status.PENDING_PAYMENT],
        "confirmed": [Booking.Status.CONFIRMED],
        "ongoing": [Booking.Status.ONGOING],
        "completed": [Booking.Status.COMPLETED],
        "cancelled": [
            Booking.Status.CANCELLED,
            Booking.Status.PAYMENT_FAILED,
            Booking.Status.EXPIRED,
        ],
    }

    @staticmethod
    def statuses_for_tab(tab: str) -> list[str] | None:
        """Returns the status list for a tab name, or None if unrecognised."""
        return BookingQueryService.TAB_STATUS_MAP.get(tab.lower())

    @staticmethod
    def get_customer_bookings(customer, tab: str):
        """
        Returns (queryset, None) on success, or (None, error_message) if
        `tab` isn't one of the recognised tab names.
        """
        statuses = BookingQueryService.statuses_for_tab(tab)
        if statuses is None:
            valid = ", ".join(BookingQueryService.TAB_STATUS_MAP.keys())
            return None, f"Invalid status filter. Must be one of: {valid}"

        return BookingRepository.get_bookings_for_customer(customer, statuses), None

    @staticmethod
    def get_booking_detail(booking_id: int, customer):
        """Returns the Booking instance, or None if not found / not owned by customer."""
        return BookingRepository.get_booking_by_id_for_customer(booking_id, customer)
