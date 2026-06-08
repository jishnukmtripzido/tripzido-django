# users/tasks.py
from celery import shared_task
from django.core.cache import cache
import requests
from django.conf import settings

# from twilio.rest import Client  # uncomment when ready


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def send_otp_sms(self, phone_number, otp):
    try:
        # --- SMS PROVIDER INTEGRATION  ---

        # response = requests.post(
        #     "https://www.fast2sms.com/dev/bulkV2",
        #     headers={"authorization": settings.FAST2SMS_API_KEY},
        #     data={
        #         "route": "otp",
        #         "variables_values": otp,
        #         "flash": 0,
        #         "numbers": phone_number,
        #     },
        #     timeout=10,  # don't wait forever
        # )

        # data = response.json()

        # print(
        #     f"Fast2SMS response for {phone_number}: {data}"
        # )  # For debugging, remove in production

        # if not data.get("return"):
        #     # Fast2SMS returned an error
        #     raise Exception(f"Fast2SMS error: {data.get('message')}")

        # # success ✅
        # return {"status": "sent", "phone": phone_number}

        # For now just print (remove in production)
        print(f"📱 Sending OTP {otp} to {phone_number}")

    except Exception as exc:
        # Auto retry up to 3 times if SMS fails
        raise self.retry(exc=exc)
