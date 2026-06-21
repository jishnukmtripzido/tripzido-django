from django.db.models import Prefetch
from apps.bookings.models import Booking
from apps.payments.models import Payment


class BookingRepository:

    @staticmethod
    def get_bookings_for_customer(customer, statuses: list[str]):
        """
        Returns the customer's bookings restricted to the given status
        list, newest first (Booking.Meta.ordering already does this),
        with everything the list/detail serializers need preloaded.
        """
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
        """
        Single booking, scoped to the requesting customer so one user
        can never fetch another user's booking by guessing an id.
        Includes payments for the detail view's payment history.
        """
        return (
            Booking.objects.filter(id=booking_id, customer=customer)
            .select_related(
                "listing__vehicle_type",
                "listing__vendor",
                "pickup_location",
                "pricing_package__package_type",
                "handed_over_by",
                "return_confirmed_by",
            )
            .prefetch_related(
                Prefetch(
                    "payments",
                    queryset=Payment.objects.order_by("-initiated_at"),
                )
            )
            .first()
        )
