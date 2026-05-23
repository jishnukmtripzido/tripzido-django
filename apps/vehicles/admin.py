from django.contrib import admin

from apps.core.admin import SoftDeleteAdmin
from apps.vehicles.models import (
    DoorstepDeliveryTier,
    PackageCategory,
    PricingPackage,
    PricingPackageType,
    VehicleImage,
    VehicleListing,
    VehicleType,
)


@admin.register(VehicleType)
class VehicleTypeAdmin(SoftDeleteAdmin):
    list_display = ("name", "brand", "make_year", "transmission_type", "fuel_type", "seats", "is_published", "is_deleted_display")
    list_filter = ("brand", "transmission_type", "fuel_type", "is_published")
    search_fields = ("name", "brand")
    readonly_fields = ("is_deleted_display",)


@admin.register(VehicleListing)
class VehicleListingAdmin(SoftDeleteAdmin):
    list_display = ("vendor", "vehicle_type", "pickup_location", "status", "available_count", "is_deleted_display")
    list_filter = ("status", "pickup_location__city", "doorstep_delivery_enabled")
    search_fields = ("vendor__business_name", "vehicle_type__name", "pickup_location__name")
    readonly_fields = ("is_deleted_display", "approved_at", "suspended_at", "paused_at")


@admin.register(PackageCategory)
class PackageCategoryAdmin(SoftDeleteAdmin):
    list_display = ("name", "sort_order", "is_deleted_display")
    search_fields = ("name",)
    readonly_fields = ("is_deleted_display",)


@admin.register(PricingPackageType)
class PricingPackageTypeAdmin(SoftDeleteAdmin):
    list_display = ("name", "category", "duration_hours", "sort_order", "is_deleted_display")
    list_filter = ("category",)
    search_fields = ("name",)
    readonly_fields = ("is_deleted_display",)


@admin.register(PricingPackage)
class PricingPackageAdmin(SoftDeleteAdmin):
    list_display = ("listing", "package_type", "duration_hours", "price", "is_deleted_display")
    list_filter = ("package_type",)
    search_fields = ("listing__vehicle_type__name",)
    readonly_fields = ("is_deleted_display",)


@admin.register(DoorstepDeliveryTier)
class DoorstepDeliveryTierAdmin(SoftDeleteAdmin):
    list_display = ("listing", "max_distance_km", "charge", "is_deleted_display")
    search_fields = ("listing__vehicle_type__name",)
    readonly_fields = ("is_deleted_display",)


@admin.register(VehicleImage)
class VehicleImageAdmin(SoftDeleteAdmin):
    list_display = ("listing", "source", "sort_order", "is_primary", "is_deleted_display")
    list_filter = ("source", "is_primary")
    search_fields = ("listing__vehicle_type__name",)
    readonly_fields = ("is_deleted_display",)
