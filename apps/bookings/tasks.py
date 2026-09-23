# apps/bookings/tasks.py

import logging
from celery import shared_task
from django.utils import timezone
from django.db import transaction

from apps.bookings.models import Booking
from apps.payments.models import Payment

logger = logging.getLogger(__name__)


@shared_task
def expire_stale_pending_bookings():
    """
    Finds every PENDING_PAYMENT booking whose expires_at has passed and
    flips it (and its associated Payment) to a terminal failed state.

    Does NOT delete rows — see reasoning in the codebase notes: keeping
    the row preserves payment/audit history and lets a late-arriving
    Cashfree webhook still reconcile against something real, rather
    than silently failing to find the order.

    Runs per booking_group_id so all bookings + the one Payment row in
    a multi-vehicle checkout are updated together and atomically.
    """
    now = timezone.now()

    stale_group_ids = (
        Booking.objects.filter(
            status=Booking.Status.PENDING_PAYMENT,
            expires_at__lt=now,
        )
        .values_list("booking_group_id", flat=True)
        .distinct()
    )

    expired_count = 0
    for group_id in stale_group_ids:
        with transaction.atomic():
            group_bookings = Booking.objects.select_for_update().filter(
                booking_group_id=group_id,
                status=Booking.Status.PENDING_PAYMENT,
                expires_at__lt=now,
            )
            if not group_bookings.exists():
                # Already handled by a webhook/poll between the query
                # above and acquiring the lock here — skip, don't double-process.
                continue

            updated = group_bookings.update(status=Booking.Status.EXPIRED)
            expired_count += updated

            Payment.objects.filter(
                booking__booking_group_id=group_id,
                status__in=[Payment.Status.INITIATED, Payment.Status.PENDING],
            ).update(
                status=Payment.Status.FAILED,
                failed_at=now,
                failure_reason="Payment window expired before completion.",
            )

    if expired_count:
        logger.info("Expired %s stale pending booking(s).", expired_count)

    return expired_count


@shared_task
def auto_cancel_no_show_bookings():
    """
    Finds every CONFIRMED booking whose dropoff_date has already passed —
    the customer never came in to pick up (or return) the vehicle — and
    cancels it so it doesn't sit in CONFIRMED forever.

    Mirrors the CONFIRMED -> CANCELLED path VendorBookingService.update_status
    takes for a manual vendor cancellation: flips status and records
    cancelled_at/cancelled_by_role only. It does not run refund/forfeiture
    accounting or create a BookingCancellation row, same as that path —
    there's nothing to refund since the trip never started.

    Compares against dropoff_date (not a combined dropoff datetime) since
    this runs once a day at midnight: by the time it runs, any CONFIRMED
    booking with a dropoff_date before today is at least a full day past
    its drop-off, so the exact drop-off time doesn't need to be checked.
    """
    today = timezone.localdate()
    now = timezone.now()

    cancelled_count = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        dropoff_date__lt=today,
    ).update(
        status=Booking.Status.CANCELLED,
        cancelled_at=now,
        cancelled_by_role=Booking.CancelledBy.SYSTEM,
    )

    if cancelled_count:
        logger.info("Auto-cancelled %s no-show confirmed booking(s).", cancelled_count)

    return cancelled_count
