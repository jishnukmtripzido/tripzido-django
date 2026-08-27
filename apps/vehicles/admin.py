from django.contrib import admin
from django.utils import timezone

from apps.core.admin import SoftDeleteAdmin
from apps.vehicles.models import (
    Brand,
    DoorstepDeliveryTier,
    PackageCategory,
    PricingPackage,
    PricingPackageType,
    VehicleImage,
    VehicleListing,
    VendorPickupPoint,
    VehicleType,
    OperatingScheduleTemplate,
    TemplateScheduleDay,
    ListingBlockedPeriod,
    VehicleReview,
    ReviewRating,
)


@admin.register(Brand)
class BrandAdmin(SoftDeleteAdmin):
    list_display = ("name", "is_deleted_display")
    search_fields = ("name",)
    readonly_fields = ("is_deleted_display",)


@admin.register(VehicleType)
class VehicleTypeAdmin(SoftDeleteAdmin):
    list_display = (
        "name",
        "brand",
        "make_year",
        "transmission_type",
        "fuel_type",
        "seats",
        "is_published",
        "is_deleted_display",
    )
    list_filter = ("brand", "transmission_type", "fuel_type", "is_published")
    search_fields = ("name", "brand")
    readonly_fields = ("is_deleted_display",)


@admin.register(VehicleListing)
class VehicleListingAdmin(SoftDeleteAdmin):
    list_display = (
        "vendor",
        "vehicle_type",
        "pickup_location",
        "schedule_template",
        "status",
        "available_count",
        "is_deleted_display",
    )
    list_filter = (
        "status",
        "pickup_location__city",
        "doorstep_delivery_enabled",
        "schedule_template",
    )
    search_fields = (
        "vendor__business_name",
        "vehicle_type__name",
        "pickup_location__name",
    )
    readonly_fields = ("is_deleted_display", "approved_at", "suspended_at", "paused_at")


@admin.register(VendorPickupPoint)
class VendorPickupPointAdmin(SoftDeleteAdmin):
    list_display = (
        "vendor",
        "pickup_location",
        "label",
        "address",
        "is_deleted_display",
    )
    list_filter = ("vendor", "pickup_location")
    search_fields = ("vendor__business_name", "label", "address")
    readonly_fields = ("is_deleted_display",)


@admin.register(PackageCategory)
class PackageCategoryAdmin(SoftDeleteAdmin):
    list_display = ("name", "sort_order", "is_deleted_display")
    search_fields = ("name",)
    readonly_fields = ("is_deleted_display",)


@admin.register(PricingPackageType)
class PricingPackageTypeAdmin(SoftDeleteAdmin):
    list_display = (
        "name",
        "category",
        "duration_hours",
        "sort_order",
        "is_deleted_display",
    )
    list_filter = ("category",)
    search_fields = ("name",)
    readonly_fields = ("is_deleted_display",)


@admin.register(PricingPackage)
class PricingPackageAdmin(SoftDeleteAdmin):
    list_display = (
        "listing",
        "package_type",
        "duration_hours",
        "price",
        "is_deleted_display",
    )
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
    list_display = (
        "listing",
        "source",
        "sort_order",
        "is_primary",
        "is_deleted_display",
    )
    list_filter = ("source", "is_primary")
    search_fields = ("listing__vehicle_type__name",)
    readonly_fields = ("is_deleted_display",)


class TemplateScheduleDayInline(admin.TabularInline):
    model = TemplateScheduleDay
    extra = 1


@admin.register(OperatingScheduleTemplate)
class OperatingScheduleTemplateAdmin(SoftDeleteAdmin):
    list_display = ("name", "vendor", "is_deleted_display")
    list_filter = ("vendor",)
    search_fields = ("name", "vendor__business_name")
    readonly_fields = ("is_deleted_display",)
    inlines = [TemplateScheduleDayInline]


@admin.register(ListingBlockedPeriod)
class ListingBlockedPeriodAdmin(SoftDeleteAdmin):
    list_display = (
        "listing",
        "start_datetime",
        "end_datetime",
        "count",
        "reason",
        "note",
    )
    list_filter = ("listing", "reason")
    search_fields = ("listing__vehicle_type__name",)
    readonly_fields = ("is_deleted_display",)


class ReviewRatingInline(admin.TabularInline):
    model = ReviewRating
    extra = 0
    min_num = 0


@admin.register(VehicleReview)
class VehicleReviewAdmin(SoftDeleteAdmin):
    inlines = [ReviewRatingInline]

    list_display = (
        "id",
        "listing",
        "customer",
        "average_rating_display",
        "moderation_status",
        "created_at",
        "moderated_by",
        "is_deleted_display",
    )
    list_filter = (
        "moderation_status",
        "ratings__criterion",
        "listing__pickup_location__city",
    )
    search_fields = (
        "listing__vehicle_type__name",
        "customer__phone_number",
        "customer__first_name",
        "customer__last_name",
        "review_text",
    )
    readonly_fields = (
        "average_rating_display",
        "created_at",
        "is_deleted_display",
    )
    fields = (
        "booking",
        "customer",
        "listing",
        "average_rating_display",
        "review_text",
        "moderation_status",
        "moderation_note",
        "moderated_by",
        "moderated_at",
        "created_at",
        "is_deleted_display",
    )
    actions = ["approve_reviews", "remove_reviews", "flag_reviews"]

    @admin.display(description="Avg Rating")
    def average_rating_display(self, obj):
        avg = obj.average_rating
        return f"{avg} ★" if avg is not None else "—"

    def _set_moderation_status(self, request, queryset, status_value, status_label):
        updated = queryset.update(
            moderation_status=status_value,
            moderated_by=request.user,
            moderated_at=timezone.now(),
        )
        self.message_user(request, f"{updated} review(s) marked as {status_label}.")

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        self._set_moderation_status(
            request, queryset, VehicleReview.ModerationStatus.APPROVED, "Approved"
        )

    @admin.action(description="Remove selected reviews")
    def remove_reviews(self, request, queryset):
        self._set_moderation_status(
            request, queryset, VehicleReview.ModerationStatus.REMOVED, "Removed"
        )

    @admin.action(description="Flag selected reviews for review")
    def flag_reviews(self, request, queryset):
        self._set_moderation_status(
            request, queryset, VehicleReview.ModerationStatus.FLAGGED, "Flagged"
        )
