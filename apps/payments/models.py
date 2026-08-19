from django.db import models
from apps.core.models import BaseModel
from apps.vendors.models import Vendor
from apps.users.models import User


# Create your models here.
class Payment(BaseModel):
    """
    Tracks every payment attempt against a booking.
    Multiple attempts allowed per booking (retry logic – US-C28).
    """

    class PaymentType(models.TextChoices):
        PARTIAL = "PARTIAL", "Partial Payment"
        FULL = "FULL", "Full Payment"
        # SECURITY_DEPOSIT = "SECURITY_DEPOSIT", "Security Deposit"
        # DOORSTEP_DELIVERY = "DOORSTEP_DELIVERY", "Doorstep Delivery Charge"

    class Status(models.TextChoices):
        INITIATED = "INITIATED", "Initiated"
        PENDING = "PENDING", "Pending (Awaiting Gateway)"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"
        PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Partially Refunded"

    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.PROTECT, related_name="payments"
    )
    booking_group_id = models.UUIDField(
        db_index=True,
        help_text="The booking_group_id of the associated booking, for easier querying across multiple payments.",
    )

    payment_type = models.CharField(max_length=25, choices=PaymentType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    # Cashfree fields
    gateway = models.CharField(max_length=50, default="CASHFREE")
    gateway_order_id = models.CharField(max_length=200, unique=True, db_index=True)
    gateway_payment_id = models.CharField(max_length=200, blank=True, db_index=True)
    gateway_response = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=25, choices=Status.choices, default=Status.INITIATED
    )

    attempt_number = models.PositiveSmallIntegerField(default=1)  # max 3 (US-C28)

    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)

    # Webhook reconciliation
    webhook_received_at = models.DateTimeField(null=True, blank=True)
    is_reconciled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-initiated_at"]
        indexes = [
            models.Index(fields=["booking", "status"]),
            models.Index(fields=["booking_group_id", "status"]),  # NEW
        ]

    def __str__(self):
        return f"Payment({self.gateway_order_id}) {self.status} ₹{self.amount}"


class VendorPayout(BaseModel):
    """
    A single manual bank transfer (settlement) made by platform staff
    to a vendor, covering one or more completed bookings' net rental
    proceeds.

    Only ever needed for payment_mode=FULL bookings — when a customer
    pays PARTIAL or PAY_AT_PICKUP, the vendor already collects their
    share of the rent directly from the customer at pickup (in cash),
    so there's nothing left for the platform to pay out for those
    bookings. See VendorPayoutItem for which specific bookings a given
    payout covers.

    This flow is entirely manual by design: staff select eligible
    bookings (via Django admin), send an actual bank transfer outside
    this system, then record the UTR + paid_at here. No payout-gateway
    integration.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Transfer"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Transfer Failed"

    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="payouts")

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )

    # Sum of this payout's VendorPayoutItem amounts. Stored (not
    # computed on the fly) so the total stays stable regardless of any
    # later change to a linked Booking — recompute_total() is the
    # only method that should ever update this, called automatically
    # by VendorPayoutAdmin after inline items are saved.
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Optional labeling for a regular weekly/monthly settlement cycle.
    # Leave blank for an ad-hoc/one-off payout.
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    # Snapshot of the vendor's bank details AT THE TIME of this
    # payout — not a live FK to BankAccount, since that can change
    # later and this transfer already happened against whatever
    # details were current when staff sent it. Expected shape:
    # {"account_holder_name": "...", "account_number": "...",
    #  "ifsc_code": "...", "bank_name": "..."}
    bank_account_snapshot = models.JSONField(default=dict, blank=True)

    utr_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Bank transfer UTR/reference number, entered once the transfer completes.",
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vendor_payouts_marked_paid",
        help_text="Staff member who recorded this payout as paid.",
    )

    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["vendor", "status"]),
        ]

    def recompute_total(self):
        total = self.items.aggregate(total=models.Sum("amount"))["total"] or 0
        self.total_amount = total
        self.save(update_fields=["total_amount"])

    def __str__(self):
        return (
            f"Payout({self.vendor.business_name}) ₹{self.total_amount} [{self.status}]"
        )


class VendorPayoutItem(BaseModel):
    """
    Links one Booking to the VendorPayout that covers it. OneToOne on
    booking — a booking can only ever appear in a single payout, which
    is what actually prevents double-paying a vendor for the same
    booking, enforced at the database level rather than by
    application logic alone.
    """

    payout = models.ForeignKey(
        VendorPayout, on_delete=models.CASCADE, related_name="items"
    )
    booking = models.OneToOneField(
        "bookings.Booking", on_delete=models.PROTECT, related_name="payout_item"
    )

    # Snapshot of the amount attributed to this booking — set from
    # booking.net_amount at creation time (see save() below) and
    # never read live off Booking again, for the same reason every
    # other financial snapshot in this codebase is stored: so this
    # number can never silently drift.
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.amount and self.booking_id:
            self.amount = self.booking.net_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"PayoutItem(booking={self.booking.booking_reference}) ₹{self.amount}"


class RefundRecord(BaseModel):
    """
    Tracks the manual refund owed to a customer for one cancelled
    booking. Auto-created (status=PENDING) the moment a
    BookingCancellation is written with money owed — see the one-line
    hook added to CancellationService._finalize_cancellation — so
    staff never manually "create" a refund; every cancellation with a
    refundable amount already has one waiting here.

    Entirely manual by design, same as VendorPayout: no gateway
    integration yet (a real Cashfree refund call is a planned,
    separate, not-yet-built piece). Staff process the actual refund
    through Cashfree's own dashboard or a bank transfer outside this
    system, then record a reference number here.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Refund"
        PROCESSED = "PROCESSED", "Refunded"
        FAILED = "FAILED", "Refund Failed"

    cancellation = models.OneToOneField(
        "bookings.BookingCancellation",
        on_delete=models.CASCADE,
        related_name="refund_record",
    )

    # Snapshot from BookingCancellation.refundable_amount at creation
    # time — never read live off cancellation again, same reasoning as
    # every other financial snapshot in this codebase.
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )

    reference_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Gateway/bank refund reference number, entered once the refund completes.",
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="refunds_marked_processed",
        help_text="Staff member who recorded this refund as processed.",
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return (
            f"Refund(booking={self.cancellation.booking.booking_reference}) "
            f"₹{self.amount} [{self.status}]"
        )
