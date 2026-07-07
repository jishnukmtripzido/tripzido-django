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
