import logging
from celery import shared_task
from apps.notifications.whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)


# @shared_task(bind=True, max_retries=3, default_retry_delay=30)
# def send_booking_confirmation_whatsapp(
#     self,
#     phone_number,
#     booking_reference,
#     vehicle_name,
#     pickup_date,
#     pickup_time,
#     pickup_location,
# ):
#     try:
#         WhatsAppClient.send_template_message(
#             to=phone_number,
#             template_name="booking_confirmation",  # must match an APPROVED template in Meta Business Manager
#             language_code="en",
#             components=[
#                 {
#                     "type": "body",
#                     "parameters": [
#                         {"type": "text", "text": booking_reference},
#                         {"type": "text", "text": vehicle_name},
#                         {"type": "text", "text": pickup_date},
#                         {"type": "text", "text": pickup_time},
#                         {"type": "text", "text": pickup_location},
#                     ],
#                 }
#             ],
#         )
#     except Exception as exc:
#         logger.warning(
#             "WhatsApp send failed for booking %s: %s", booking_reference, exc
#         )
#         raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_booking_confirmation_whatsapp(
    self,
    phone_number,
    booking_reference,
    vehicle_name,
    pickup_date,
    pickup_time,
    pickup_location,
):
    try:
        WhatsAppClient.send_template_message(
            to=phone_number,
            template_name="hello_world",  # ← TEMP: swap back to "booking_confirmation" once that's approved
            language_code="en_US",  # ← matches "English (US)" in your screenshot
            components=[],  # hello_world has no body variables
        )
    except Exception as exc:
        logger.warning(
            "WhatsApp send failed for booking %s: %s", booking_reference, exc
        )
        raise self.retry(exc=exc)
