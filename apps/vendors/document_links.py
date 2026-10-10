from django.core import signing
from django.urls import reverse
from django.utils.http import urlencode

# Vendor KYC documents live in private storage (see core.storage) and
# are only reachable through a short-lived signed link. The link goes
# out only in API responses that already passed the vendor-owner /
# staff permission checks, so the signature itself is the access
# check at download time — which lets the frontend keep using a plain
# <a href> / window.open, no Authorization header needed.

LINK_SALT = "vendors.document-file"
LINK_MAX_AGE = 60 * 60  # 1 hour


def build_document_url(doc, request=None) -> str | None:
    if not doc.file:
        return None
    token = signing.dumps(doc.pk, salt=LINK_SALT)
    path = (
        reverse("vendor-document-file", args=[doc.pk])
        + "?"
        + urlencode({"token": token})
    )
    return request.build_absolute_uri(path) if request is not None else path


def check_document_token(doc_id: int, token: str) -> str | None:
    """Returns an error message, or None if the token is valid for doc_id."""
    if not token:
        return "Missing download token."
    try:
        signed_id = signing.loads(token, salt=LINK_SALT, max_age=LINK_MAX_AGE)
    except signing.SignatureExpired:
        return "This download link has expired. Refresh the page to get a new one."
    except signing.BadSignature:
        return "Invalid download link."
    if signed_id != doc_id:
        return "Invalid download link."
    return None
