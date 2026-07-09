from django.db import models
from apps.core.models import BaseModel
from apps.users.models import User

# Create your models here.


class VendorCommission(BaseModel):
    """
    Defines a commission structure.
    Referenced by SubscriptionPlan.
    Can be flat percentage or tiered based on booking volume.
    """

    class CommissionType(models.TextChoices):
        FLAT = "FLAT", "Flat Percentage"
        # TIERED = "TIERED", "Tiered (Volume Based)"

    name = models.CharField(max_length=100)  # e.g. "Standard 10%", "Premium 7%"
    commission_type = models.CharField(
        max_length=10, choices=CommissionType.choices, default=CommissionType.FLAT
    )

    # Used when commission_type = FLAT
    flat_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="e.g. 10.00 means 10%",
    )

    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.commission_type})"


class SubscriptionPlan(BaseModel):
    """
    Plans offered to vendors. Each plan defines:
      - What features the vendor gets
      - How many listings they can create
      - Which commission structure applies
      - Billing cycle and price
    """

    class BillingCycle(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        YEARLY = "YEARLY", "Yearly"
        LIFETIME = "LIFETIME", "Lifetime (One Time)"

    name = models.CharField(max_length=100)  # e.g. "Starter", "Growth", "Pro"
    description = models.TextField(blank=True)
    billing_cycle = models.CharField(max_length=15, choices=BillingCycle.choices)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    # Commission structure tied to this plan
    commission = models.ForeignKey(
        VendorCommission, on_delete=models.PROTECT, related_name="subscription_plans"
    )

    # Feature limits
    max_listings = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Max vehicle listings allowed. NULL = unlimited",
    )
    max_pickup_locations = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Max pickup locations allowed. NULL = unlimited",
    )
    max_images_per_listing = models.PositiveIntegerField(default=10)

    # Feature flags — what this plan unlocks
    # can_enable_doorstep_delivery = models.BooleanField(default=False)
    can_enable_partial_payment = models.BooleanField(default=True)
    can_access_analytics = models.BooleanField(default=False)
    can_respond_to_reviews = models.BooleanField(default=True)
    priority_listing = models.BooleanField(
        default=False, help_text="Listings appear higher in search results"
    )

    is_default = models.BooleanField(
        default=False, help_text="Auto-assigned to new vendors if no plan is selected"
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price"]

    def __str__(self):
        return f"{self.name} ({self.billing_cycle}) ₹{self.price}"

    def save(self, *args, **kwargs):
        if self.is_default:
            SubscriptionPlan.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class Vendor(BaseModel):
    """
    Vendor profile. One User → one Vendor.
    Status tracks the onboarding / operational state.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Admin Approval"
        APPROVED = "APPROVED", "Approved & Active"
        REJECTED = "REJECTED", "Rejected"
        SUSPENDED = "SUSPENDED", "Suspended"
        BANNED = "BANNED", "Permanently Banned"

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="vendor_profile"
    )

    # Business details
    business_name = models.CharField(max_length=200)
    owner_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=15)  # primary business contact
    address = models.TextField()
    gst_number = models.CharField(max_length=20, blank=True)  # optional

    # Logo
    logo_image = models.ImageField(upload_to="vendor/logos/", null=True, blank=True)

    # Operational status
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    rejection_reason = models.TextField(blank=True)

    # Admin who approved/rejected/suspended
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vendors_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.TextField(blank=True)
    suspended_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vendors_suspended",
    )

    banned_at = models.DateTimeField(null=True, blank=True)
    ban_reason = models.TextField(blank=True)
    banned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vendors_banned",
    )

    # Vendor-level T&C applies to all their vehicles (US-V10)
    # terms_and_conditions = models.TextField(blank=True)
    tc_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.business_name} ({self.status})"


class VendorDocument(BaseModel):
    """
    Documents uploaded during vendor onboarding (ID proof, business reg, etc.).
    """

    class DocType(models.TextChoices):
        BUSINESS_REGISTRATION = "BUSINESS_REGISTRATION", "Business Registration"
        ID_PROOF = "ID_PROOF", "ID Proof"
        GST_CERTIFICATE = "GST_CERTIFICATE", "GST Certificate"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Review"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="documents"
    )
    doc_type = models.CharField(max_length=30, choices=DocType.choices)
    file = models.FileField(upload_to="vendor/documents/")
    original_filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.vendor.business_name} – {self.doc_type}"


class BankAccount(BaseModel):
    """
    Vendor bank account for payouts (US-V16).
    A new record is created on each change; previous records archived.
    Changes require admin re-verification before use.
    """

    class Status(models.TextChoices):
        PENDING_VERIFICATION = "PENDING", "Pending Admin Verification"
        VERIFIED = "VERIFIED", "Verified – Active"
        REJECTED = "REJECTED", "Rejected"
        SUPERSEDED = "SUPERSEDED", "Superseded by Newer Record"

    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="bank_accounts"
    )
    account_holder_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50)  # store encrypted in production
    ifsc_code = models.CharField(max_length=11)
    bank_name = models.CharField(max_length=200, blank=True)
    branch_name = models.CharField(max_length=200, blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING_VERIFICATION
    )
    is_active_acc = models.BooleanField(
        default=False
    )  # only one row is active at a time

    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bank_accounts_verified",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # Was a payout cycle active when this change was submitted?
    pending_cycle_flag = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.vendor.business_name} – {self.account_number[-4:]} ({self.status})"
        )

    def save(self, *args, **kwargs):
        if self.is_active_acc:
            BankAccount.objects.filter(vendor=self.vendor, is_active_acc=True).update(
                is_active_acc=False
            )
        super().save(*args, **kwargs)


class VendorSubscription(BaseModel):
    """
    Tracks which plan a vendor is currently on and the full history.
    One ACTIVE row per vendor at any time.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"
        PENDING_PAYMENT = "PENDING_PAYMENT", "Pending Payment"
        GRACE_PERIOD = "GRACE_PERIOD", "Grace Period (Payment Overdue)"

    vendor = models.ForeignKey(
        "Vendor", on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.PROTECT, related_name="vendor_subscriptions"
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT
    )

    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # NULL for LIFETIME plans
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    # Payment reference for this subscription cycle
    payment_reference = models.CharField(max_length=200, blank=True)
    amount_paid = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    is_current = models.BooleanField(default=True)

    # Who assigned this (admin manual assignment or system auto)
    assigned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="subscriptions_assigned",
    )
    is_manually_assigned = models.BooleanField(
        default=False,
        help_text="True if admin manually overrode the plan instead of vendor purchasing it",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["vendor", "is_current", "status"]),
        ]

    def save(self, *args, **kwargs):
        if self.is_current:
            VendorSubscription.objects.filter(
                vendor=self.vendor, is_current=True
            ).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vendor.business_name} → {self.plan.name} ({self.status})"


class VendorTerms(BaseModel):
    """
    Vendor-defined T&C and 'Things to Remember' for a listing (US-V10).
    Versioned: a new record is created on every update.
    """

    listing = models.ForeignKey(
        "vehicles.VehicleListing", on_delete=models.CASCADE, related_name="vendor_terms"
    )
    terms_items = models.JSONField(default=list)

    # Structured "Things to Remember" (US-C07)
    security_deposit_note = models.TextField(blank=True)
    operating_hours_note = models.TextField(blank=True)
    distance_limit_note = models.TextField(blank=True)
    excess_charge_note = models.TextField(blank=True)
    late_penalty_note = models.TextField(blank=True)

    is_current = models.BooleanField(
        default=True, db_index=True
    )  # only latest is current
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-version"]
        indexes = [
            models.Index(fields=["listing", "is_current"]),
        ]

    def save(self, *args, **kwargs):
        latest_version = (
            VendorTerms.objects.filter(listing=self.listing)
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
            or 0
        )

        if self.pk is not None:
            # Editing an existing record should create a new versioned row.
            self.version = latest_version + 1
            self.pk = None
            self._state.adding = True
            self.is_current = True
        elif latest_version and self.version <= latest_version:
            self.version = latest_version + 1

        if self.is_current:
            VendorTerms.objects.filter(listing=self.listing, is_current=True).update(
                is_current=False
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"VendorTerms({self.listing}) v{self.version}"
