from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Max
from apps.core.models import BaseModel

User = get_user_model()

# Register your models here.


class CancellationPolicy(BaseModel):
    """
    Platform-wide cancellation policy, versioned.
    The policy snapshot applicable at booking time is stored per booking.
    """

    name = models.CharField(max_length=50)
    is_current = models.BooleanField(default=True, db_index=True)
    refund_note = models.CharField(max_length=300)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"],
                condition=models.Q(is_current=True),
                name="unique_current_cancellation_policy",
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk is None:
            last_version = CancellationPolicy.objects.aggregate(
                max_version=Max("version")
            )["max_version"]
            self.version = (last_version or 0) + 1

        if self.is_current:
            CancellationPolicy.objects.filter(is_current=True).exclude(
                pk=self.pk
            ).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"CancellationPolicy v{self.version} (current={self.is_current})"


class CancellationTier(BaseModel):
    policy = models.ForeignKey(
        CancellationPolicy, on_delete=models.CASCADE, related_name="tiers"
    )
    min_hours_before_pickup = models.PositiveIntegerField(
        help_text="Hours before pickup time (lower bound of this tier)"
    )
    max_hours_before_pickup = models.PositiveIntegerField(
        null=True, blank=True, help_text="Upper bound (NULL = no upper limit)"
    )
    refund_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="0 = full forfeiture, 100 = full refund",
    )
    label = models.CharField(
        max_length=150,
        blank=True,
        help_text="e.g. 'More than 48 hours before pickup'. Auto-generated if left blank.",
    )
    description = models.CharField(
        max_length=300,
        blank=True,
        help_text="e.g. 'Full refund of advance payment.' Auto-generated if left blank.",
    )

    class Meta:
        ordering = ["-min_hours_before_pickup"]

    def __str__(self):
        return (
            f"Tier({self.policy}) "
            f"{self.min_hours_before_pickup}–{self.max_hours_before_pickup or '∞'} hrs "
            f"→ {self.refund_percentage}% refund"
        )
