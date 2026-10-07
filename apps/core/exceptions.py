from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """
    Gives errors DRF raises itself (expired token, PermissionDenied from
    a permission class or AuditJWTAuthentication, NotFound, throttling…)
    the same {"success", "message", "errors"} shape as
    core.responses.error_response, so frontends that read `message`
    show the real reason instead of a generic "API error: 403".

    Additive only: DRF's original body is kept as-is (including
    `detail`, which some frontends read), and responses views build
    themselves via error_response never pass through here.
    """
    response = exception_handler(exc, context)
    if response is None or not isinstance(response.data, dict):
        return response

    data = response.data
    if "message" not in data:
        detail = data.get("detail")
        if detail is not None:
            data["message"] = str(detail)
        elif isinstance(exc, ValidationError):
            # Field errors ({"field": [...]}) — same wording views use.
            data["message"] = "Invalid data"
        else:
            data["message"] = "Request failed"
    data.setdefault("success", False)
    data.setdefault("errors", [])
    return response
