from contextvars import ContextVar
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
    def authenticate(self, request):
        result = super().authenticate(request)
        _current_actor.set(result[0] if result else None)
        return result
