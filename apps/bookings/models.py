from django.db import models
from apps.core.models import BaseModel

# Create your models here.


class Booking(BaseModel):
    """
    Central reservation record.

    Lifecycle:
      PENDING_PAYMENT → CONFIRMED → ONGOING → COMPLETED
                      ↘ CANCELLED (customer, vendor, or admin)
                      ↘ PAYMENT_FAILED
                      ↘ EXPIRED  (pending booking not paid in time)
    """

    # class Status(models.TextChoices):
    #     PENDING_PAYMENT = "PENDING_PAYMENT", "Pending Payment"
    #     CONFIRMED = "CONFIRMED", "Confirmed (Upcoming)"
    #     ONGOING = "ONGOING", "Ongoing"
    #     COMPLETED = "COMPLETED", "Completed"
    #     CANCELLED = "CANCELLED", "Cancelled"
    #     PAYMENT_FAILED = "PAYMENT_FAILED", "Payment Failed"
    #     EXPIRED = "EXPIRED", "Expired (Unpaid)"

    # class PaymentMode(models.TextChoices):
    #     FULL = "FULL", "Full Payment"
    #     PARTIAL = "PARTIAL", "Partial Payment"
    #     PAY_AT_PICKUP = "PAY_AT_PICKUP", "Pay at Pickup"

    # class CancelledBy(models.TextChoices):
    #     CUSTOMER = "CUSTOMER", "Customer"
    #     VENDOR = "VENDOR", "Vendor"
    #     ADMIN = "ADMIN", "Admin"
    #     SYSTEM = "SYSTEM", "System (Auto)"

    # Reference number shown to users
    booking_reference = models.CharField(max_length=20, unique=True, db_index=True)

    # customer = models.ForeignKey(
    #     User, on_delete=models.PROTECT, related_name="bookings"
    # )
    # listing = models.ForeignKey(
    #     VehicleListing, on_delete=models.PROTECT, related_name="bookings"
    # )
    # pickup_location = models.ForeignKey(
    #     PickupLocation, on_delete=models.PROTECT, related_name="bookings"
    # )

    # # Dates
    # pickup_date = models.DateField()
    # pickup_time = models.TimeField()
    # dropoff_date = models.DateField()
    # dropoff_time = models.TimeField()

    # # Counts (for bulk booking – US-C13)
    # # Count will always be one  , easier for cancellation
    # vehicle_count = models.PositiveIntegerField(default=1)

    # # Pricing snapshot (frozen at booking time so edits don't affect past bookings)
    # pricing_package = models.ForeignKey(
    #     PricingPackage,
    #     null=True,
    #     blank=True,
    #     on_delete=models.SET_NULL,
    #     related_name="bookings",
    # )
    # price_snapshot = models.JSONField(default=dict)  # full breakdown frozen at checkout
    # commission_percentage = models.DecimalField(max_digits=3, decimal_places=2)
    # listing_amount = models.DecimalField(max_digits=12, decimal_places=2)
    # commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    # discount_amount_on_commission = models.DecimalField(
    #     max_digits=12, decimal_places=2, default=0
    # )
    # net_commission_amount = models.DecimalField(max_digits=12, decimal_fields=2)
    # net_amount = models.DecimalField(max_digits=12, decimal_places=2)

    # security_deposit_amount = models.DecimalField(
    #     max_digits=10, decimal_places=2, default=0
    # )

    # payment_mode = models.CharField(
    #     max_length=20, choices=PaymentMode.choices, default=PaymentMode.FULL
    # )
    # advance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # # Coupon
    # coupon = models.ForeignKey(
    #     "coupon.Coupon",
    #     null=True,
    #     blank=True,
    #     on_delete=models.SET_NULL,
    #     related_name="bookings",
    # )
    # coupon_snapshot = models.JSONField(
    #     default=dict
    # )  # full breakdown frozen at checkout
    # coupon_discount_amount = models.DecimalField(
    #     max_digits=10, decimal_places=2, default=0
    # )

    # # T&C accepted at time of booking (snapshot of which version was accepted)
    # platform_tc_version = models.CharField(max_length=50, blank=True)
    # vendor_terms_version = models.ForeignKey(
    #     VendorTerms,
    #     null=True,
    #     blank=True,
    #     on_delete=models.SET_NULL,
    #     related_name="bookings_accepted",
    # )
    # tc_accepted_at = models.DateTimeField(null=True, blank=True)

    # # Cancellation policy snapshot
    # cancellation_policy_snapshot = models.JSONField(
    #     default=dict
    # )  # tiers frozen at booking time

    # status = models.CharField(
    #     max_length=20,
    #     choices=Status.choices,
    #     default=Status.PENDING_PAYMENT,
    #     db_index=True,
    # )

    # # Vendor operations (US-V12)
    # handed_over_at = models.DateTimeField(null=True, blank=True)
    # handed_over_by = models.ForeignKey(
    #     User,
    #     null=True,
    #     blank=True,
    #     on_delete=models.SET_NULL,
    #     related_name="bookings_handed_over",
    # )
    # returned_at = models.DateTimeField(null=True, blank=True)
    # return_confirmed_by = models.ForeignKey(
    #     User,
    #     null=True,
    #     blank=True,
    #     on_delete=models.SET_NULL,
    #     related_name="bookings_returned",
    # )

    # # Cancellation
    # cancelled_at = models.DateTimeField(null=True, blank=True)
    # cancelled_by_role = models.CharField(
    #     max_length=10, choices=CancelledBy.choices, blank=True
    # )

    # # Expiry for pending bookings (US-A18 configurable)
    # expires_at = models.DateTimeField(null=True, blank=True)

    # class Meta:
    #     ordering = ["-created_at"]
    #     indexes = [
    #         models.Index(fields=["customer", "status"]),
    #         models.Index(fields=["listing", "status"]),
    #         models.Index(fields=["pickup_datetime", "dropoff_datetime"]),
    #     ]

    # def __str__(self):
    #     return f"Booking({self.booking_reference}) {self.status}"
