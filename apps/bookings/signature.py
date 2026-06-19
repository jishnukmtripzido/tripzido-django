import hmac
import hashlib
import base64
import time
from django.conf import settings


def verify_cashfree_signature(raw_body: bytes, timestamp: str, signature: str) -> bool:
    """
    Per Cashfree's documented process: concatenate timestamp + raw body
    (exact, unparsed), HMAC-SHA256 with the secret key, base64-encode,
    compare to the x-webhook-signature header.
    """
    if not timestamp or not signature:
        return False

    # Reject stale webhooks — defends against replay if a payload is
    # ever captured and resent. 5 minutes is a conventional window.
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except (TypeError, ValueError):
        return False

    payload = timestamp + raw_body.decode("utf-8")
    computed = base64.b64encode(
        hmac.new(
            settings.CASHFREE_SECRET_KEY.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    return hmac.compare_digest(computed, signature)
