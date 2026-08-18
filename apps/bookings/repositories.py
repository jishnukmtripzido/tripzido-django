from django.db.models import Prefetch
from apps.bookings.models import Booking, BookingCancellation
from apps.payments.models import Payment


class BookingRepository:

    @staticmethod
    def get_bookings_for_customer(customer, statuses: list[str]):
        return Booking.objects.filter(
            customer=customer, status__in=statuses
        ).select_related(
            "listing__vehicle_type",
            "listing__vendor",
            "pickup_location",
            "pricing_package__package_type",
        )

    @staticmethod
    def get_booking_by_id_for_customer(booking_id: int, customer):
        return (
            Booking.objects.filter(id=booking_id, customer=customer)
            .select_related(
                "listing__vehicle_type",
                "listing__vendor",
                "listing__pickup_point",
                "pickup_location",
                "pricing_package__package_type",
                "handed_over_by",
                "return_confirmed_by",
                "cancellation",
            )
            .prefetch_related(
                Prefetch(
                    "payments",
                    queryset=Payment.objects.order_by("-initiated_at"),
                )
            )
            .first()
        )

    @staticmethod
    def get_bookings_by_group(group_id, customer):
        return (
            Booking.objects.filter(booking_group_id=group_id, customer=customer)
            .select_related(
                "listing__vehicle_type",
                "listing__vendor",
                "pickup_location",
                "pricing_package__package_type",
            )
            .order_by("created_at")
        )


class BookingCancellationRepository:

    @staticmethod
    def create_cancellation_record(**fields) -> BookingCancellation:
        return BookingCancellation.objects.create(**fields)

    @staticmethod
    def get_cancellation_for_booking(booking_id: int):
        return BookingCancellation.objects.filter(booking_id=booking_id).first()


class VendorBookingRepository:

    @staticmethod
    def get_bookings_for_vendor(vendor_id: int, statuses: list[str] | None = None):
        """
        Every booking whose listing belongs to this vendor, newest
        first (Booking.Meta.ordering already sorts -created_at).
        statuses=None returns every status — the "All" filter tab.
        """
        qs = Booking.objects.filter(listing__vendor_id=vendor_id).select_related(
            "listing__vehicle_type",
            "pickup_location",
            "customer",
            "pricing_package__package_type",
        )
        if statuses:
            qs = qs.filter(status__in=statuses)
        return qs

    @staticmethod
    def get_booking_by_id_for_vendor(booking_id: int, vendor_id: int):
        """
        Ownership enforced via listing__vendor_id in the filter itself
        — a booking belonging to a different vendor's listing simply
        doesn't match, same IDOR-safe pattern used throughout the fleet
        endpoints.
        """
        return (
            Booking.objects.filter(id=booking_id, listing__vendor_id=vendor_id)
            .select_related(
                "listing__vehicle_type",
                "listing__vendor",
                "pickup_location",
                "customer",
                "pricing_package__package_type",
                "handed_over_by",
                "return_confirmed_by",
                "cancellation",
            )
            .first()
        )
