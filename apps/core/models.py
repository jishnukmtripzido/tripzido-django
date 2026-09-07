# core/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import PermissionsMixin, AbstractBaseUser
from apps.core.audit import get_current_actor


class SoftDeleteManager(models.Manager):
    """
    Custom manager that returns only active (non-deleted) records.
    This is the default manager for SoftDeleteModel and its subclasses.
    """

    def get_queryset(self):
        """Return a queryset filtered to only include active (non-soft-deleted) objects."""
        return super().get_queryset().filter(is_active=True)


class AllObjectsManager(models.Manager):
    """
    Custom manager that returns all records, including soft-deleted ones.
    Use this when you need access to deleted records (e.g. audit logs, restore flows).
    """

    def get_queryset(self):
        """Return an unfiltered queryset including soft-deleted objects."""
        return super().get_queryset()


class SoftDeleteModel(models.Model):
    """
    Abstract base model that provides soft-delete functionality.
    Instead of permanently removing records from the database, soft-delete
    marks them as inactive and records who deleted them and when.

    Managers:
        objects     -- default, excludes soft-deleted records
        all_objects -- includes soft-deleted records
    """

    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_deleted_by",
    )
    is_active = models.BooleanField(default=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, deleted_by=None, *args, **kwargs):
        """
        Soft-delete this object by marking it inactive and recording metadata.
        Does NOT remove the record from the database.

        Args:
            deleted_by: The user instance responsible for the deletion. Defaults to None.
        """
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.is_active = False
        self.save(update_fields=["deleted_at", "deleted_by", "is_active"])

    def hard_delete(self, *args, **kwargs):
        """
        Permanently delete this object from the database.
        This action is irreversible. Use with caution.
        """
        super().delete(*args, **kwargs)

    def restore(self):
        """
        Restore a soft-deleted object by marking it active again
        and clearing the deletion metadata.
        """
        self.deleted_at = None
        self.deleted_by = None
        self.is_active = True
        self.save(update_fields=["deleted_at", "deleted_by", "is_active"])

    @property
    def is_deleted(self):
        """
        Check whether this object has been soft-deleted.
        """
        return not self.is_active


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        actor = get_current_actor()
        if actor is not None and "last_updated_by" not in kwargs:
            kwargs["last_updated_by"] = actor
        return super().update(**kwargs)


class AuditManager(SoftDeleteManager.from_queryset(AuditQuerySet)):
    def bulk_create(self, objs, **kwargs):
        actor = get_current_actor()
        if actor is not None:
            for obj in objs:
                if obj.created_by_id is None:
                    obj.created_by = actor
                obj.last_updated_by = actor
        return super().bulk_create(objs, **kwargs)


class BaseModel(SoftDeleteModel):
    """
    Abstract base model that extends SoftDeleteModel with audit trail fields.
    Tracks who created and last updated each record, and when.
    Inherit from this model for any model that needs full audit + soft-delete support.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="%(class)s_created_by",
    )
    last_updated_at = models.DateTimeField(auto_now=True)
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="%(class)s_last_updated_by",
    )

    objects = AuditManager()

    def save(self, *args, **kwargs):
        actor = get_current_actor()
        if actor is not None:
            if self._state.adding and self.created_by_id is None:
                self.created_by = actor
            self.last_updated_by = actor

            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"last_updated_by"}
                if self._state.adding and self.created_by_id is not None:
                    kwargs["update_fields"].add("created_by")

        return super().save(*args, **kwargs)

    class Meta:
        abstract = True
