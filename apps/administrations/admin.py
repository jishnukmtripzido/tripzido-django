from django.contrib import admin
from django.utils.html import format_html
from apps.core.admin import SoftDeleteAdmin
from django_summernote.admin import SummernoteModelAdmin
from apps.administrations.models import (
    AnnouncementBanner,
    CancellationPolicy,
    CancellationTier,
    Offer,
    PopularRental,
)


@admin.register(AnnouncementBanner)
class AnnouncementBannerAdmin(SummernoteModelAdmin):
    summernote_fields = ("content",)
    list_display = ["page", "is_current", "is_active", "created_at"]
    list_filter = ["page", "is_current", "is_active"]
    list_editable = ["is_current"]
    readonly_fields = ["created_at", "last_updated_at"]
    fieldsets = (
        (
            None,
            {
                "fields": ("page", "is_current", "content"),
            },
        ),
        (
            "Meta",
            {
                "fields": ("is_active", "created_at", "last_updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


class CancellationTierInline(admin.TabularInline):
    model = CancellationTier
    extra = 1
    fields = (
        "min_hours_before_pickup",
        "max_hours_before_pickup",
        "refund_percentage",
        "label",
        "description",
    )


@admin.register(CancellationPolicy)
class CancellationPolicyAdmin(SoftDeleteAdmin):
    list_display = (
        "name",
        "version",
        "is_current",
        "refund_note",
        "is_deleted_display",
    )
    list_filter = ("is_current",)
    search_fields = ("name",)
    readonly_fields = ("version", "is_deleted_display")
    inlines = [CancellationTierInline]


@admin.register(Offer)
class OfferAdmin(SoftDeleteAdmin):
    list_display = (
        "title",
        "coupon_code",
        "discount_amount",
        "min_order_amount",
        "is_active",
        "sort_order",
        "valid_from",
        "valid_until",
        "is_deleted_display",
    )
    list_filter = ("is_active", "icon_type")
    search_fields = ("title", "coupon_code")
    list_editable = ("sort_order", "is_active")
    readonly_fields = ("is_deleted_display",)
    fieldsets = (
        (
            "Basic Info",
            {
                "fields": (
                    "title",
                    "description",
                    "icon_type",
                    "sort_order",
                    "is_active",
                ),
            },
        ),
        (
            "Discount",
            {
                "fields": ("coupon_code", "discount_amount", "min_order_amount"),
            },
        ),
        (
            "Validity",
            {
                "fields": ("valid_from", "valid_until"),
            },
        ),
    )


@admin.register(PopularRental)
class PopularRentalAdmin(SoftDeleteAdmin):
    list_display = (
        "vehicle_type",
        "city",
        "display_name",
        "display_price",
        "tag",
        "sort_order",
        "is_deleted_display",
        "pickup_location",
    )
    list_filter = ("city",)
    search_fields = ("vehicle_type__name", "city__name", "display_name")
    list_editable = ("sort_order",)
    readonly_fields = ("is_deleted_display",)
    fieldsets = (
        (
            "Linking",
            {
                "fields": ("city", "vehicle_type", "pickup_location"),
            },
        ),
        (
            "Card Overrides",
            {
                "fields": ("display_name", "display_price", "display_image", "tag"),
                "description": "All fields here are optional — each falls back to the linked VehicleType value when left blank.",
            },
        ),
        (
            "Ordering",
            {
                "fields": ("sort_order",),
            },
        ),
    )
