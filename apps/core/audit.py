from contextvars import ContextVar
from rest_framework.exceptions import AuthenticationFailed
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
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        # Check vendor status dynamically on every request
        vendor = user.get_vendor_profile()
        if vendor is not None and vendor.status != vendor.Status.APPROVED:
            raise AuthenticationFailed(
                "This vendor account is no longer active.",
                code="vendor_inactive",
            )

        return user

    def authenticate(self, request):
        result = super().authenticate(request)
        _current_actor.set(result[0] if result else None)
        return result
