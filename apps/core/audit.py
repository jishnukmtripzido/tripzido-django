from contextvars import ContextVar
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from rest_framework_simplejwt.authentication import JWTAuthentication

_current_actor = ContextVar("current_audit_actor", default=None)


def get_current_actor():
    return _current_actor.get()


class AuditActorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _current_actor.set(None)
        try:
            return self.get_response(request)
        finally:
            _current_actor.set(None)


class AuditJWTAuthentication(JWTAuthentication):
    """
    Extends JWTAuthentication to:
    1. Bind the authenticated user to `_current_actor` for audit logs.
    2. Enforce real-time vendor status verification on every authenticated request.

    Vendor status rules, checked on every request so a status change
    takes effect immediately, even for tokens issued before it:
      - APPROVED: full access.
      - SUSPENDED: read-only, except views that set
        `allowed_for_suspended_vendor = True`. Suspension stops new
        bookings only — existing bookings carry on — so a suspended
        vendor still has to hand over, complete, or cancel them.
      - Anything else (BANNED, PENDING, REJECTED): rejected outright.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        # Check vendor status dynamically on every request
        vendor = user.get_vendor_profile()
        if vendor is not None and vendor.status not in (
            vendor.Status.APPROVED,
            vendor.Status.SUSPENDED,
        ):
            raise AuthenticationFailed(
                "This vendor account is no longer active.",
                code="vendor_inactive",
            )

        # Reused by authenticate() so the vendor isn't resolved twice.
        user._auth_vendor = vendor
        return user

    def authenticate(self, request):
        result = super().authenticate(request)
        _current_actor.set(result[0] if result else None)
        if result:
            self._enforce_suspended_vendor_read_only(request, result[0])
        return result

    @staticmethod
    def _enforce_suspended_vendor_read_only(request, user):
        if request.method in SAFE_METHODS:
            return
        vendor = getattr(user, "_auth_vendor", None)
        if vendor is None or vendor.status != vendor.Status.SUSPENDED:
            return

        # Default-deny: any write view not explicitly opted in is
        # blocked, so new vendor endpoints are covered automatically.
        view = (getattr(request, "parser_context", None) or {}).get("view")
        if getattr(view, "allowed_for_suspended_vendor", False):
            return

        # 403, not AuthenticationFailed — the token is still valid, and
        # a 401 would make the frontend log the vendor out.
        raise PermissionDenied(
            "Your vendor account is suspended. You can still manage your "
            "existing bookings; contact support for anything else.",
            code="vendor_suspended",
        )
