from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Max
from apps.core.models import BaseModel
from apps.locations.models import PickupLocation
from django.core.exceptions import ValidationError

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

    class PaymentMode(models.TextChoices):
        FULL = "FULL", "Full Payment"
        PARTIAL = "PARTIAL", "Partial Payment"

    policy = models.ForeignKey(
        CancellationPolicy, on_delete=models.CASCADE, related_name="tiers"
    )
    payment_mode = models.CharField(
        max_length=10,
        choices=PaymentMode.choices,
        default=PaymentMode.FULL,
        db_index=True,
        help_text="Which payment mode's refund schedule this tier belongs to.",
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
        max_length=150, blank=True, help_text="Auto-generated if left blank."
    )
    description = models.CharField(
        max_length=300, blank=True, help_text="Auto-generated if left blank."
    )

    class Meta:
        ordering = ["payment_mode", "-min_hours_before_pickup"]
        constraints = [
            # Prevents two tiers in the same policy+payment_mode from
            # starting at the exact same hour boundary. Doesn't catch
            # partial overlaps (e.g. 0-30 and 24-48) — that's handled
            # by clean()/the admin formset, since it needs to compare
            # against sibling rows, not just column values.
            models.UniqueConstraint(
                fields=["policy", "payment_mode", "min_hours_before_pickup"],
                name="unique_tier_start_per_policy_mode",
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.max_hours_before_pickup is not None
            and self.max_hours_before_pickup <= self.min_hours_before_pickup
        ):
            raise ValidationError(
                "max_hours_before_pickup must be greater than min_hours_before_pickup."
            )

        if self.policy_id is None:
            return

        siblings = CancellationTier.objects.filter(
            policy_id=self.policy_id, payment_mode=self.payment_mode
        )
        if self.pk:
            siblings = siblings.exclude(pk=self.pk)

        lo = self.min_hours_before_pickup
        hi = self.max_hours_before_pickup  # None = infinity

        for other in siblings:
            o_lo = other.min_hours_before_pickup
            o_hi = other.max_hours_before_pickup

            # Two half-open ranges [lo, hi) and [o_lo, o_hi) overlap iff
            # lo < o_hi (or o_hi is None) and o_lo < hi (or hi is None).
            overlaps = (o_hi is None or lo < o_hi) and (hi is None or o_lo < hi)
            if overlaps:
                raise ValidationError(
                    f"This tier's range overlaps an existing {self.payment_mode} "
                    f"tier ({o_lo}–{o_hi or '∞'} hrs) on this policy."
                )

    def __str__(self):
        return (
            f"Tier({self.policy}) [{self.payment_mode}] "
            f"{self.min_hours_before_pickup}–{self.max_hours_before_pickup or '∞'} hrs "
            f"→ {self.refund_percentage}% refund"
        )


# ── Offers ────────────────────────────────────────────────────────────


class Offer(BaseModel):
    """
    Promotional offer card shown in the "Ride more, pay less" section.

    The card with the lowest sort_order is automatically the "featured"
    (yellow) card — controlled by OfferService annotating is_featured=True
    on the first item. Admin reorders cards by editing sort_order values.
    """

    class IconType(models.TextChoices):
        STAR = "STAR", "Star"
        CALCULATOR = "CALCULATOR", "Calculator"
        LIGHTNING = "LIGHTNING", "Lightning Bolt"
        BELL = "BELL", "Bell"
        COIN = "COIN", "Coin / Rupee"

    title = models.CharField(max_length=200)
    description = models.TextField(
        help_text="Short benefit description shown on the card."
    )
    icon_type = models.CharField(
        max_length=20,
        choices=IconType.choices,
        default=IconType.STAR,
        help_text="SVG icon rendered on the frontend. STAR is used for the featured yellow card.",
    )
    coupon_code = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional coupon code the customer enters at checkout.",
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Flat discount in ₹.",
    )
    min_order_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum booking value to unlock this offer.",
    )
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
        help_text="Lowest sort_order = featured (yellow) card.",
    )

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.title


# ── Popular Rentals ───────────────────────────────────────────────────


class PopularRental(BaseModel):
    """
    A curated VehicleType pinned to a City for the "Popular rentals in
    <City>" homepage carousel.

    display_name / display_price / display_image / tag are all optional
    overrides — each falls back to the linked VehicleType's value when blank.
    """

    city = models.ForeignKey(
        "locations.City",
        on_delete=models.CASCADE,
        related_name="popular_rentals",
    )
    pickup_location = models.ForeignKey(
        PickupLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="popular_rentals",
        help_text="Optional. Pin a specific pickup location for this card. "
        "Falls back to the vendor's primary location if left blank.",
    )
    vehicle_type = models.ForeignKey(
        "vehicles.VehicleType",
        on_delete=models.CASCADE,
        related_name="popular_rentals",
    )
    display_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Override for the card title. Falls back to VehicleType.name.",
    )
    display_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="'Starting from' price shown on the card. Falls back to VehicleType's cheapest live package.",
    )
    display_image = models.ImageField(
        upload_to="popular_rentals/",
        null=True,
        blank=True,
        help_text="Card image override. Falls back to VehicleType.primary_image.",
    )
    tag = models.CharField(
        max_length=50,
        blank=True,
        help_text="Badge text shown on the card e.g. 'Best Seller', 'New'.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)

    class Meta:
        unique_together = ("city", "vehicle_type")
        ordering = ["city", "sort_order", "created_at"]

    def __str__(self):
        return f"{self.vehicle_type} — {self.city.name}"


class AnnouncementBanner(BaseModel):
    """
    Page-specific announcement banner shown at the top of a page.
    Only one banner per page can be current (is_current=True).
    Content is rich HTML — bold, links, etc — sized by frontend Tailwind classes.
    """

    class Page(models.TextChoices):
        SEARCH_RESULT = "search_result", "Search Result Page"
        VEHICLE_DETAIL = "vehicle_detail", "Vehicle Detail Page"
        HOME = "home", "Home Page"

    content = models.TextField(
        help_text="Rich HTML content. Use the editor to add bold, links, etc. "
        "Font size is controlled by the frontend."
    )
    page = models.CharField(
        max_length=50,
        choices=Page.choices,
        db_index=True,
        help_text="Which page this banner appears on.",
    )
    is_current = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Only one banner per page can be current at a time.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["page"],
                condition=models.Q(is_current=True, is_active=True),
                name="unique_current_active_banner_per_page",
            )
        ]

    def save(self, *args, **kwargs):
        # when setting a banner as current, unset all others for that page
        if self.is_current:
            AnnouncementBanner.objects.filter(page=self.page, is_current=True).exclude(
                pk=self.pk
            ).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        status = "current" if self.is_current else "inactive"
        return f"Banner [{self.get_page_display()}] ({status})"
