from django.db import models
from apps.core.models import BaseModel


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
        "bookings.Booking", on_delete=models.CASCADE, related_name="payments"
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
        ]

    def __str__(self):
        return f"Payment({self.gateway_order_id}) {self.status} ₹{self.amount}"
