import logging
from apps.logs.models import LoginLog, ActivityLog

logger = logging.getLogger(__name__)


class LoginLogService:
    @staticmethod
    def record(portal, identifier, success, user=None, failure_reason="", request=None):
        try:
            LoginLog.objects.create(
                user=user,
                portal=portal,
                identifier_attempted=identifier,
                success=success,
                failure_reason=failure_reason,
                ip_address=request.META.get("REMOTE_ADDR") if request else None,
                user_agent=(
                    request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""
                ),
            )
        except Exception:
            logger.exception("Failed to record login log")


class ActivityLogService:
    @staticmethod
    def log(
        actor,
        actor_role,
        action,
        target_model="",
        target_id=None,
        target_label="",
        description="",
        metadata=None,
        request=None,
    ):
        try:
            ActivityLog.objects.create(
                actor=actor,
                actor_role=actor_role,
                action=action,
                target_model=target_model,
                target_id=target_id,
                target_label=target_label,
                description=description,
                metadata=metadata or {},
                ip_address=request.META.get("REMOTE_ADDR") if request else None,
            )
        except Exception:
            logger.exception("Failed to record activity log")
