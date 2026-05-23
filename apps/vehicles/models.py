from django.db import models
from apps.core.models import BaseModel
from apps.users.models import User
from apps.vendors.models import Vendor
from apps.locations.models import PickupLocation
from datetime import time

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

    # Core specs (US-C07, US-A01)
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, db_index=True)
    make_year = models.PositiveIntegerField()
    transmission_type = models.CharField(
        max_length=20, choices=TransmissionType.choices
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

    available_count = models.PositiveIntegerField(default=1)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_APPROVAL,
        db_index=True,
    )
    rejection_reason = models.TextField(blank=True)

    # Admin approval
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="listings_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Suspension
    suspended_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="listings_suspended",
    )
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.TextField(blank=True)

    # Vendor-pause
    paused_at = models.DateTimeField(null=True, blank=True)

    # Security deposit (shown in price breakdown – US-C07)
    security_deposit_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )

    # Doorstep delivery toggle (US-C10)
    doorstep_delivery_enabled = models.BooleanField(default=False)

    # Pay-at-pickup option
    pay_at_pickup_enabled = models.BooleanField(default=False)

    # Km limit and excess charge (shown in US-C07, US-C31)
    km_limit_per_day = models.PositiveIntegerField(null=True, blank=True)
    excess_charge_per_km = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )


    # Late return penalty
    late_return_penalty_per_hour = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    # Operating hours
    operating_hours_start = models.TimeField(null=True, blank=True)
    operating_hours_end = models.TimeField(null=True, blank=True)

    # Partial payment toggle (US-C09)
    partial_payment_enabled = models.BooleanField(default=True)
    partial_payment_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="% of total to collect upfront when partial payment selected",
    )

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
    name = models.CharField(max_length=50, unique=True)        # "Hourly", "Daily"
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
        on_delete=models.PROTECT,          # prevent deleting "Daily" if packages exist
        related_name="package_types"
    )
    name = models.CharField(max_length=50, unique=True)        # "3-Hour", "6-Hour"
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
    # is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("listing", "package_type")

    def __str__(self):
        return f"{self.listing} – {self.package_type} @ ₹{self.price}"


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
