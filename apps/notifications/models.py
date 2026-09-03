from django.db import models
from apps.core.models import BaseModel
from apps.users.models import User


class Notification(BaseModel):
    """
    One row per recipient per event — an admin-facing notification for
    an event that concerns 3 staff members creates 3 rows, not 1. This
    is the simpler of two real options (the other being one shared row
    per event + a separate per-user read-tracking join table), and the
    right one at this platform's scale: a handful of staff/vendor
    accounts, not millions of recipients where duplicating a row per
    person would actually matter.

    title/message are rendered to plain text ONCE, at creation time —
    not recomputed from the underlying booking/listing on every read.
    This keeps the notification historically accurate even if the
    underlying object is later edited or deleted, and avoids an extra
    join back to that object every time a notification list renders.

    link is a plain relative path (e.g. "/bookings/detail?id=123"),
    not a GenericForeignKey. Nothing here needs "find every
    notification about object X" — only "take me to the right page on
    click" — so a plain string does the job without the extra query
    complexity a GFK would add.
    """

    class NotificationType(models.TextChoices):
        NEW_BOOKING = "NEW_BOOKING", "New Booking"
        LISTING_SUBMITTED = "LISTING_SUBMITTED", "Listing Submitted for Review"
        LISTING_APPROVED = "LISTING_APPROVED", "Listing Approved"
        LISTING_REJECTED = "LISTING_REJECTED", "Listing Rejected"
        LISTING_SUSPENDED = "LISTING_SUSPENDED", "Listing Suspended"
        BOOKING_CANCELLED = "BOOKING_CANCELLED", "Booking Cancelled"
        PAYOUT_PAID = "PAYOUT_PAID", "Payout Paid"
        PAYOUT_FAILED = "PAYOUT_FAILED", "Payout Failed"
        # Add new event types here as they're built — each is just a
        # new choice + one call site, never a schema change.

    class Portal(models.TextChoices):
        VENDOR = "VENDOR", "Vendor Portal"
        ADMIN = "ADMIN", "Admin Portal"
        CUSTOMER = "CUSTOMER", "Customer Portal"

    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications", db_index=True
    )
    portal = models.CharField(
        max_length=20,
        choices=Portal.choices,
        db_index=True,
    )
    notification_type = models.CharField(
        max_length=30, choices=NotificationType.choices, db_index=True
    )
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    link = models.CharField(
        max_length=255,
        blank=True,
        help_text="Relative frontend path to navigate to on click, e.g. /bookings/detail?id=123",
    )

    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
        ]

    def __str__(self):
        return (
            f"{self.recipient} — {self.title} [{'read' if self.is_read else 'unread'}]"
        )
