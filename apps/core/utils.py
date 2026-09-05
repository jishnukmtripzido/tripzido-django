from django.utils import timezone
from datetime import datetime


def parse_client_datetime(value: str) -> datetime:
    """
    Safely parses a client-submitted ISO datetime string into an aware
    datetime, regardless of whether the string includes a timezone
    offset or not — mirrors what DRF's DateTimeField does
    automatically everywhere else in this codebase.
    datetime.fromisoformat() alone does NOT do this: given a
    naive-looking string, it silently returns a naive datetime with no
    warning — the same bug class already found and fixed in the
    booking display serializers, except here it can affect a WRITE
    path (real booking creation), not just display.

    Also explicitly normalizes a trailing "Z" (UTC) suffix — before
    Python 3.11, datetime.fromisoformat() couldn't parse "Z" at all
    and raised ValueError outright, which JS's Date.toISOString()
    commonly produces.
    """
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed
