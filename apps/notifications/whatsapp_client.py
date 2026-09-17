import requests
from django.conf import settings


class WhatsAppClient:
    """
    Thin wrapper around the WhatsApp Cloud API's /messages endpoint.
    Same shape as apps/bookings/cashfree_client.py — no retry logic here,
    that belongs in the Celery task that calls this.
    """

    @staticmethod
    def _url() -> str:
        return (
            f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}"
            f"/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        )

    @staticmethod
    def _headers() -> dict:
        return {
            "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def send_template_message(
        to: str, template_name: str, language_code: str, components: list
    ) -> dict:
        """
        Sends a pre-approved WhatsApp template message.
        `components` follows Meta's template shape, e.g.:
            [{"type": "body", "parameters": [{"type": "text", "text": "..."}]}]
        Raises on non-2xx — caller (the task) handles retry.
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        }
        response = requests.post(
            WhatsAppClient._url(),
            json=payload,
            headers=WhatsAppClient._headers(),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
