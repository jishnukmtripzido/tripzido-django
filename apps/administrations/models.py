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


class LegalDocument(BaseModel):
    """
    Versioned legal documents: Platform T&C and Privacy Policy.
    Each save() creates a new version (immutable history) — same
    pattern as CancellationPolicy, scoped per doc_type since PLATFORM_TC
    and PRIVACY_POLICY each need their own independent version sequence
    and their own "current" row.
    """

    class DocType(models.TextChoices):
        PLATFORM_TC = "PLATFORM_TC", "Platform Terms & Conditions"
        PRIVACY_POLICY = "PRIVACY_POLICY", "Privacy Policy"

    doc_type = models.CharField(max_length=20, choices=DocType.choices, db_index=True)
    version = models.PositiveIntegerField(default=1)
    content = models.TextField()  # Rich text / HTML / Markdown
    is_current = models.BooleanField(default=False, db_index=True)

    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legal_docs_published",
    )

    class Meta:
        unique_together = ("doc_type", "version")
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["doc_type"],
                condition=models.Q(is_current=True),
                name="unique_current_legal_document_per_type",
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk is None:
            last_version = LegalDocument.objects.filter(
                doc_type=self.doc_type
            ).aggregate(max_version=Max("version"))["max_version"]
            self.version = (last_version or 0) + 1

        if self.is_current:
            LegalDocument.objects.filter(
                doc_type=self.doc_type, is_current=True
            ).exclude(pk=self.pk).update(is_current=False)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"LegalDoc({self.doc_type}) v{self.version} current={self.is_current}"


class CustomerTCAcceptance(BaseModel):
    """
    Records when a customer accepted a version of a platform legal
    document. Re-acceptance is required whenever a new version is
    published (US-A19) — get_or_create at booking time means a repeat
    customer under the same still-current version doesn't error or
    duplicate; it just confirms the existing acceptance stands.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="tc_acceptances"
    )
    legal_document = models.ForeignKey(
        LegalDocument, on_delete=models.PROTECT, related_name="acceptances"
    )
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "legal_document")

    def __str__(self):
        return f"TCAccept({self.user.phone_number} v{self.legal_document.version})"


class PlatformConfig(BaseModel):
    """
    Key-value store for runtime platform settings managed by admin.
    Changes go live immediately without code deployment.

    Example keys:
      DEFAULT_COMMISSION_PERCENTAGE
      OTP_EXPIRY_MINUTES
      OTP_MAX_RESEND_ATTEMPTS
      PENDING_BOOKING_EXPIRY_MINUTES
      MIN_BOOKING_DURATION_HOURS
      SUPPORT_TICKET_AUTO_CLOSE_DAYS
      REFUND_TIMELINE_DAYS
      COMPLAINT_WINDOW_DAYS
      VENDOR_CANCELLATION_POLICY_HOURS_THRESHOLD
      MAX_RETRY_PAYMENT_ATTEMPTS
    """

    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    data_type = models.CharField(
        max_length=20,
        choices=[
            ("STRING", "String"),
            ("INTEGER", "Integer"),
            ("DECIMAL", "Decimal"),
            ("BOOLEAN", "Boolean"),
            ("JSON", "JSON"),
        ],
        default="STRING",
    )

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"Config({self.key}) = {self.value[:60]}"


from django.db.models import Max


class TaxRate(BaseModel):
    """
    Platform-wide tax rate, versioned — same pattern as
    CancellationPolicy / LegalDocument. Every admin change creates a
    new row instead of mutating an old one, so past bookings can
    snapshot the exact rate that applied to them and stay correct even
    after the rate changes later.

    Two independent contexts, deliberately kept separate:

      VENDOR_RENTAL
        Tax on the rental service the *vendor* sells to the customer.
        The vendor is the legal supplier of this service — this rate
        exists so the platform can calculate/display/collect it
        correctly on the vendor's behalf, not because the platform
        owes this tax itself.

      PLATFORM_COMMISSION
        Tax on the commission/facilitation service the *platform*
        sells to the vendor. This is the platform's own tax liability.

    Keeping these as two rows (rather than one flat "tax %" field)
    means a change to your commission-service tax rate never
    accidentally touches vendor rental tax, and vice versa.
    """

    class Context(models.TextChoices):
        VENDOR_RENTAL = "VENDOR_RENTAL", "Vendor Rental Service"
        PLATFORM_COMMISSION = "PLATFORM_COMMISSION", "Platform Commission Service"

    context = models.CharField(max_length=25, choices=Context.choices, db_index=True)
    name = models.CharField(max_length=100)  # e.g. "GST 18%"

    # Overall rate, plus the CGST/SGST/IGST split. The split isn't
    # needed for the arithmetic (percentage alone is enough to compute
    # amounts) but Indian GST invoices need it shown, so it's captured
    # here rather than recomputed ad hoc at invoice time.
    percentage = models.DecimalField(max_digits=5, decimal_places=2)  # e.g. 18.00
    cgst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sgst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    igst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    hsn_sac_code = models.CharField(
        max_length=20,
        blank=True,
        help_text="HSN/SAC code for invoicing, e.g. 9973 (rental services) or 9985 (support services). Confirm the correct code with your CA.",
    )

    is_current = models.BooleanField(default=True, db_index=True)
    version = models.PositiveIntegerField(default=1)
    effective_from = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["context"],
                condition=models.Q(is_current=True),
                name="unique_current_tax_rate_per_context",
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk is None:
            last_version = TaxRate.objects.filter(context=self.context).aggregate(
                max_version=Max("version")
            )["max_version"]
            self.version = (last_version or 0) + 1

        if self.is_current:
            TaxRate.objects.filter(context=self.context, is_current=True).exclude(
                pk=self.pk
            ).update(is_current=False)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"TaxRate({self.context}) v{self.version} {self.percentage}%"
