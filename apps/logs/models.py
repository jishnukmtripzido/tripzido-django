from django.db import models
from apps.users.models import User


class LoginLog(models.Model):
    class Portal(models.TextChoices):
        VENDOR = "VENDOR", "Vendor Portal"
        ADMIN = "ADMIN", "Admin Portal"
        CUSTOMER = "CUSTOMER", "Customer Portal"

    # Nullable + SET_NULL, deliberately not PROTECT — a failed login
    # with a wrong email/phone never resolves to a real user at all,
    # and even a successful login's user might be deleted later; the
    # log entry should survive either way, not block deletion.
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="login_logs",
    )
    portal = models.CharField(max_length=20, choices=Portal.choices, db_index=True)

    identifier_attempted = models.CharField(max_length=100)

    success = models.BooleanField(db_index=True)
    failure_reason = models.CharField(max_length=100, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class ActivityLog(models.Model):
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_logs",
    )
    # Snapshotted at the time of the action, not looked up live later —
    # roles can change (a team member deactivated, a staff role
    # changed), and the log should reflect what was true WHEN the
    # action happened.
    actor_role = models.CharField(max_length=50, blank=True)

    action = models.CharField(max_length=50, db_index=True)

    target_model = models.CharField(max_length=50, blank=True)
    target_id = models.IntegerField(null=True, blank=True)
    target_label = models.CharField(max_length=200, blank=True)

    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["target_model", "target_id"])]
