from django.db import models

from apps.core.models import BaseModel
import uuid

# Import related models
from apps.users.models import User
from apps.vehicles.models import VehicleListing, PricingPackage, PickupLocation
from apps.vendors.models import VendorTerms

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

    class Status(models.TextChoices):
        PENDING_PAYMENT = "PENDING_PAYMENT", "Pending Payment"
        CONFIRMED = "CONFIRMED", "Confirmed (Upcoming)"
        ONGOING = "ONGOING", "Ongoing"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        PAYMENT_FAILED = "PAYMENT_FAILED", "Payment Failed"
        EXPIRED = "EXPIRED", "Expired (Unpaid)"

    class PaymentMode(models.TextChoices):
        FULL = "FULL", "Full Payment"
        PARTIAL = "PARTIAL", "Partial Payment"
        PAY_AT_PICKUP = "PAY_AT_PICKUP", "Pay at Pickup"

    class CancelledBy(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        VENDOR = "VENDOR", "Vendor"
        ADMIN = "ADMIN", "Admin"
        SYSTEM = "SYSTEM", "System (Auto)"

    booking_group_id = models.UUIDField(db_index=True, default=uuid.uuid4)
    booking_reference = models.CharField(max_length=20, unique=True, db_index=True)

    customer = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="bookings"
    )
    listing = models.ForeignKey(
        VehicleListing, on_delete=models.PROTECT, related_name="bookings"
    )
    pickup_location = models.ForeignKey(
        PickupLocation, on_delete=models.PROTECT, related_name="bookings"
    )

    # Dates
    pickup_date = models.DateField()
    pickup_time = models.TimeField()
    dropoff_date = models.DateField()
    dropoff_time = models.TimeField()

    # Counts (for bulk booking – US-C13)
    # Count will always be one  , easier for cancellation
    vehicle_count = models.PositiveIntegerField(default=1)

    # Pricing snapshot (frozen at booking time so edits don't affect past bookings)
    pricing_package = models.ForeignKey(
        PricingPackage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bookings",
    )
    price_snapshot = models.JSONField(default=dict)  # full breakdown frozen at checkout
    commission_percentage = models.DecimalField(max_digits=5, decimal_places=2)

    listing_amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount_on_commission = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    net_commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)

    security_deposit_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )

    payment_mode = models.CharField(
        max_length=20, choices=PaymentMode.choices, default=PaymentMode.FULL
    )
    advance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    vendor_tax_rate = models.ForeignKey(
        "administrations.TaxRate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="bookings_as_vendor_tax",
        limit_choices_to={"context": "VENDOR_RENTAL"},
    )
    vendor_tax_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    vendor_tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    commission_tax_rate = models.ForeignKey(
        "administrations.TaxRate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="bookings_as_commission_tax",
        limit_choices_to={"context": "PLATFORM_COMMISSION"},
    )
    commission_tax_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    commission_tax_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    # customer_payable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # vendor_payout_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    tax_snapshot = models.JSONField(default=dict, blank=True)

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

    # T&C accepted at time of booking (snapshot of which version was accepted)
    # platform_tc_version = models.CharField(max_length=50, blank=True)
    platform_tc_document = models.ForeignKey(
        "administrations.LegalDocument",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="bookings_accepted",
    )
    vendor_terms_version = models.ForeignKey(
        VendorTerms,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="bookings_accepted",
    )
    tc_accepted_at = models.DateTimeField(null=True, blank=True)
    # Content snapshots, frozen at booking time. The FKs above are
    # already effectively immutable (VendorTerms/LegalDocument only add
    # new versions, never mutate old ones, and PROTECT blocks deletion),
    # so these aren't required for correctness — they exist so (a)
    # historical content can be read in bulk without an extra join per
    # booking, and (b) the record survives even a queryset-level
    # `.update()` on VendorTerms/LegalDocument that bypasses save()
    # entirely and would otherwise mutate a "historical" row in place.
    vendor_terms_snapshot = models.JSONField(default=dict, blank=True)
    platform_tc_snapshot = models.JSONField(default=dict, blank=True)

    # Cancellation policy snapshot
    cancellation_policy_snapshot = models.JSONField(
        default=dict
    )  # tiers frozen at booking time

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
        db_index=True,
    )

    # Vendor operations (US-V12)
    handed_over_at = models.DateTimeField(null=True, blank=True)
    handed_over_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bookings_handed_over",
    )
    returned_at = models.DateTimeField(null=True, blank=True)
    return_confirmed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bookings_returned",
    )

    # Cancellation
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by_role = models.CharField(
        max_length=10, choices=CancelledBy.choices, blank=True
    )

    # Expiry for pending bookings (US-A18 configurable)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["listing", "status"]),
            models.Index(fields=["pickup_date", "dropoff_date"]),
            models.Index(fields=["booking_group_id"]),
            models.Index(fields=["listing", "dropoff_date", "pickup_date"]),
        ]

    def __str__(self):
        return f"Booking({self.booking_reference}) {self.status}"


class BookingCancellation(BaseModel):
    """
    Cancellation detail record linked to a booking — one per booking.
    Captures who cancelled, why, and the refund entitlement computed at
    cancellation time. `policy_version` snapshots
    administrations.CancellationPolicy.version at the moment of
    cancellation (not a live FK) so that later policy edits — including
    the auto-versioning CancellationPolicy.save() does on every active
    policy change — never alter the numbers on a past cancellation.

    Reason codes intentionally include vendor/admin-only values
    (VENDOR_BREAKDOWN, VENDOR_EMERGENCY, ADMIN_ACTION) even though the
    customer-facing cancel endpoint only accepts a trimmed subset
    (CHANGE_OF_PLANS, FOUND_BETTER, BOOKED_BY_MISTAKE, TRIP_CANCELLED,
    OTHER) — see CustomerCancelBookingSerializer / CUSTOMER_REASON_CODES
    below. Keeping the full enum here means this same model can be
    reused once vendor- or admin-initiated cancellation is built,
    without a migration.
    """

    class CancellationReason(models.TextChoices):
        CHANGE_OF_PLANS = "CHANGE_OF_PLANS", "Change of Plans"
        FOUND_BETTER = "FOUND_BETTER", "Found a Better Option"
        BOOKED_BY_MISTAKE = "BOOKED_BY_MISTAKE", "Booked by Mistake"
        TRIP_CANCELLED = "TRIP_CANCELLED", "Trip Cancelled"
        VENDOR_BREAKDOWN = "VENDOR_BREAKDOWN", "Vehicle Breakdown"
        VENDOR_EMERGENCY = "VENDOR_EMERGENCY", "Vendor Emergency"
        ADMIN_ACTION = "ADMIN_ACTION", "Admin Action"
        OTHER = "OTHER", "Other"

    # Customer-initiated cancellation may only use these reason codes.
    CUSTOMER_REASON_CODES = [
        CancellationReason.CHANGE_OF_PLANS,
        CancellationReason.FOUND_BETTER,
        CancellationReason.BOOKED_BY_MISTAKE,
        CancellationReason.TRIP_CANCELLED,
        CancellationReason.OTHER,
    ]

    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name="cancellation"
    )
    cancelled_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="cancellations_initiated"
    )
    cancelled_by_role = models.CharField(
        max_length=20, choices=Booking.CancelledBy.choices
    )
    reason_code = models.CharField(max_length=30, choices=CancellationReason.choices)
    reason_text = models.TextField(blank=True)  # free text, mainly for OTHER

    # Snapshot of administrations.CancellationPolicy.version at
    # cancellation time — intentionally NOT a ForeignKey, since that
    # policy is versioned-and-replaced (see CancellationPolicy.save())
    # and we want this number frozen regardless of later policy changes.
    policy_version = models.PositiveIntegerField(null=True, blank=True)
    hours_before_pickup_at_cancellation = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    # Refund entitlement at time of cancellation
    refund_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    refundable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    forfeited_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Cancellation({self.booking.booking_reference}) by {self.cancelled_by_role}"
