from django.db import models
from apps.core.models import BaseModel
from apps.users.models import User
from apps.vendors.models import Vendor
from apps.locations.models import PickupLocation
from datetime import time
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator


# Create your models here.
class VehicleType(BaseModel):
    """
    Master vehicle catalogue entry created by Tripzido admin.
    Vendors pick from this catalogue; they cannot create new vehicle types.
    """

    class TransmissionType(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        AUTOMATIC = "AUTOMATIC", "Automatic"
        SEMI_AUTOMATIC = "SEMI_AUTO", "Semi-Automatic"

    class FuelType(models.TextChoices):
        PETROL = "PETROL", "Petrol"
        ELECTRIC = "ELECTRIC", "Electric"
        CNG = "CNG", "CNG"
        HYBRID = "HYBRID", "Hybrid"
        DIESEL = "DIESEL", "Diesel"

    class VehicleTypeChoices(models.TextChoices):
        CAR = "CAR", "Car"
        BIKE = "BIKE", "Bike"
        SCOOTER = "SCOOTER", "Scooter"
        AUTO_RICKSHAW = "AUTO", "Auto Rickshaw"
        BUS = "BUS", "Bus"
        VAN = "VAN", "Van"

    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, db_index=True)
    make_year = models.PositiveIntegerField()
    transmission_type = models.CharField(
        max_length=20, choices=TransmissionType.choices
    )
    vehicle_type = models.CharField(
        max_length=50,
        default=VehicleTypeChoices.SCOOTER,
        db_index=True,
        choices=VehicleTypeChoices.choices,
    )
    primary_image = models.ImageField(
        upload_to="vehicle_type/images/", null=True, blank=True
    )
    fuel_type = models.CharField(max_length=20, choices=FuelType.choices)
    seats = models.PositiveSmallIntegerField()
    cc = models.PositiveIntegerField(help_text="Engine displacement in cc")
    top_speed_kmph = models.PositiveIntegerField(null=True, blank=True)
    fuel_capacity_litres = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    weight_kg = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )
    mileage_kmpl = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    is_published = models.BooleanField(default=False, db_index=True)

    class Meta:
        unique_together = ("name", "make_year")
        ordering = ["brand", "name"]

    def __str__(self):
        return f"{self.brand} {self.name} ({self.make_year})"


class OperatingScheduleTemplate(BaseModel):
    """
    Reusable weekly schedule owned by a vendor (e.g. "Standard Hours",
    "Weekend Hours"). A vendor creates these once and assigns them to
    as many listings as they like via VehicleListing.schedule_template,
    instead of repeating the same 7-day schedule on every listing
    individually.
    """

    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="schedule_templates"
    )
    name = models.CharField(max_length=100)  # e.g. "Standard Hours"

    class Meta:
        unique_together = ("vendor", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.vendor.business_name} – {self.name}"


class TemplateScheduleDay(BaseModel):
    """
    One weekday entry within an OperatingScheduleTemplate. Replaces the
    old per-listing ListingOperatingSchedule — same shape, but keyed to
    a shared template instead of a single listing.

    If a day has no entry → that day is unavailable, same rule as
    before. A listing with no template assigned at all is treated as
    closed every day.
    """

    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    template = models.ForeignKey(
        OperatingScheduleTemplate, on_delete=models.CASCADE, related_name="days"
    )
    day_of_week = models.IntegerField(choices=DayOfWeek.choices)

    open_time = models.TimeField(default=time(7, 0))
    close_time = models.TimeField(default=time(19, 0))

    is_closed = models.BooleanField(
        default=False,
        help_text="If True, listings using this template are fully unavailable this day regardless of times",
    )

    class Meta:
        unique_together = ("template", "day_of_week")
        ordering = ["day_of_week"]


class VehicleListing(BaseModel):
    """
    A vendor's listing of a specific VehicleType at a specific PickupLocation.
    This is the bookable unit.

    One vendor can list the same vehicle type at multiple locations,
    each with its own price and available count.
    """

    class Status(models.TextChoices):
        PENDING_APPROVAL = "PENDING", "Pending Admin Approval"
        APPROVED = "APPROVED", "Approved – Active"
        PAUSED = "PAUSED", "Paused by Vendor"
        SUSPENDED = "SUSPENDED", "Suspended by Admin"
        REJECTED = "REJECTED", "Rejected"

    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="vehicle_listings"
    )
    vehicle_type = models.ForeignKey(
        VehicleType, on_delete=models.PROTECT, related_name="listings"
    )
    pickup_location = models.ForeignKey(
        PickupLocation, on_delete=models.PROTECT, related_name="vehicle_listings"
    )

    # Reusable weekly schedule. NULL = no schedule assigned yet, which
    # is treated as closed every day (same fail-safe as a listing
    # missing a day entry under the old per-listing model).
    schedule_template = models.ForeignKey(
        OperatingScheduleTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="listings",
    )

    available_count = models.PositiveIntegerField(default=1)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_APPROVAL,
        db_index=True,
    )
    rejection_reason = models.TextField(blank=True)

    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="listings_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    suspended_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="listings_suspended",
    )
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.TextField(blank=True)

    paused_at = models.DateTimeField(null=True, blank=True)

    security_deposit_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )

    doorstep_delivery_enabled = models.BooleanField(default=False)

    km_limit_per_day = models.PositiveIntegerField(null=True, blank=True)
    excess_charge_per_km = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    late_return_penalty_per_hour = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    # Display-only fallback hours shown on the listing card/detail page
    # when there's no current VendorTerms note — unrelated to the
    # day-by-day booking schedule above, which is what actually gates
    # availability.
    operating_hours_start = models.TimeField(null=True, blank=True)
    operating_hours_end = models.TimeField(null=True, blank=True)

    class Meta:
        unique_together = ("vendor", "vehicle_type", "pickup_location")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.vendor.business_name} | {self.vehicle_type} @ {self.pickup_location}"


class PackageCategory(BaseModel):
    """
    Admin-managed list of package categories.
    e.g. Hourly, Daily, Weekly, Monthly etc.
    """

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class PricingPackageType(BaseModel):
    """
    Master list of package types (hourly, half-day, daily, etc.).
    Allows admin to manage available package types across the platform.
    """

    category = models.ForeignKey(
        PackageCategory,
        on_delete=models.PROTECT,
        related_name="package_types",
    )
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    duration_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Standard duration in hours for this package type",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.duration_hours}h)"


class PricingPackage(BaseModel):
    """
    Pricing packages per listing: e.g. hourly, half-day, daily (US-C08).
    Multiple packages per listing allowed.
    """

    listing = models.ForeignKey(
        VehicleListing, on_delete=models.CASCADE, related_name="pricing_packages"
    )
    package_type = models.ForeignKey(
        PricingPackageType, on_delete=models.PROTECT, related_name="pricing_packages"
    )
    duration_hours = models.DecimalField(max_digits=5, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    pay_at_pickup_enabled = models.BooleanField(default=False)
    partial_payment_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="% of total to collect upfront when partial payment selected",
    )
    km_limit = models.PositiveIntegerField(default=None, null=True, blank=True)

    class Meta:
        unique_together = ("listing", "package_type")

    def __str__(self):
        return f"{self.listing} – {self.package_type} @ ₹{self.price}"


class ListingBlockedPeriod(BaseModel):
    """
    Specific date/time blocks — maintenance, holidays, personal use.
    Overrides the recurring schedule for that period.

    `count` is how many units of the fleet this block takes out of
    service (e.g. 1 scooter sent for repair out of a fleet of 3) — it
    no longer blocks the entire listing regardless of fleet size.
    """

    class BlockReason(models.TextChoices):
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        PERSONAL_USE = "PERSONAL_USE", "Personal Use"
        HOLIDAY = "HOLIDAY", "Holiday Closure"
        OTHER = "OTHER", "Other"

    listing = models.ForeignKey(
        VehicleListing, on_delete=models.CASCADE, related_name="blocked_periods"
    )
    start_datetime = models.DateTimeField(db_index=True)
    end_datetime = models.DateTimeField()
    count = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    reason = models.CharField(
        max_length=20, choices=BlockReason.choices, default=BlockReason.OTHER
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["start_datetime"]
        indexes = [models.Index(fields=["listing", "start_datetime", "end_datetime"])]

    def clean(self):
        if self.end_datetime <= self.start_datetime:
            raise ValidationError("end_datetime must be after start_datetime")

        if self.listing_id and self.count > self.listing.available_count:
            raise ValidationError(
                "count cannot exceed the listing's total fleet size "
                f"({self.listing.available_count})."
            )

        overlapping = ListingBlockedPeriod.objects.filter(
            listing=self.listing,
            start_datetime__lt=self.end_datetime,
            end_datetime__gt=self.start_datetime,
        ).exclude(pk=self.pk)

        if overlapping.exists():
            raise ValidationError("Overlaps with an existing blocked period.")


class DoorstepDeliveryTier(BaseModel):
    """
    Tiered doorstep delivery charges by distance (US-C10).
    e.g. ₹50 up to 5 km, ₹100 up to 10 km.
    """

    listing = models.ForeignKey(
        VehicleListing, on_delete=models.CASCADE, related_name="delivery_tiers"
    )
    max_distance_km = models.PositiveIntegerField(
        help_text="Upper bound of this tier in km"
    )
    charge = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        ordering = ["max_distance_km"]
        unique_together = ("listing", "max_distance_km")

    def __str__(self):
        return f"{self.listing} – up to {self.max_distance_km} km → ₹{self.charge}"


class VehicleImage(BaseModel):
    """
    Images for a VehicleListing.
    Both admin/catalogue images and vendor-uploaded images (US-C07).
    """

    class ImageSource(models.TextChoices):
        ADMIN = "ADMIN", "Admin (Catalogue)"
        VENDOR = "VENDOR", "Vendor Uploaded"

    listing = models.ForeignKey(
        VehicleListing, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="vehicle/images/")
    source = models.CharField(
        max_length=10, choices=ImageSource.choices, default=ImageSource.VENDOR
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vehicle_images_uploaded",
    )

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"Image({self.listing}) #{self.sort_order}"


class VehicleReview(BaseModel):
    """
    Customer review for a completed booking.
    One review per booking (enforced at model level).
    """

    class ModerationStatus(models.TextChoices):
        PENDING = "PENDING", "Pending Moderation"
        APPROVED = "APPROVED", "Approved – Visible"
        REMOVED = "REMOVED", "Removed by Admin"
        FLAGGED = "FLAGGED", "Flagged for Review"

    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.CASCADE, related_name="reviews"
    )
    customer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reviews_given"
    )
    listing = models.ForeignKey(
        VehicleListing, on_delete=models.CASCADE, related_name="reviews"
    )

    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    review_text = models.TextField(blank=True)

    moderation_status = models.CharField(
        max_length=20,
        choices=ModerationStatus.choices,
        default=ModerationStatus.PENDING,
    )
    moderation_note = models.TextField(blank=True)
    moderated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviews_moderated",
    )
    moderated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Review(booking={self.booking_id}) {self.rating}★"
