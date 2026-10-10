import ipaddress

from rest_framework.throttling import BaseThrottle


def get_client_ip(request) -> str | None:
    """
    The real client IP, accounting for nginx in front of gunicorn.

    Delegates to DRF's own BaseThrottle.get_ident so login logs, OTP
    limits and DRF throttling always agree on who the client is. With
    REST_FRAMEWORK["NUM_PROXIES"] = 1 it takes the address nginx
    appended to X-Forwarded-For (not anything the client put there),
    and falls back to REMOTE_ADDR when the header is absent, e.g.
    under local runserver.

    Returns None rather than a malformed value, since callers store
    this in GenericIPAddressField columns.
    """
    ident = BaseThrottle().get_ident(request)
    try:
        return str(ipaddress.ip_address(ident))
    except ValueError:
        return None
