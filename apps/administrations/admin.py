from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from apps.core.admin import SoftDeleteAdmin
from django_summernote.admin import SummernoteModelAdmin
from apps.administrations.models import (
    AnnouncementBanner,
    CancellationPolicy,
    CancellationTier,
    LegalDocument,
    Offer,
    PlatformConfig,
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
        (None, {"fields": ("page", "is_current", "content")}),
        (
            "Meta",
            {
                "fields": ("is_active", "created_at", "last_updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


class CancellationTierInlineFormSet(forms.BaseInlineFormSet):
    """
    Validates across all tier rows submitted together for one policy:
    - no two rows in the same payment_mode overlap in their hour range
    - max_hours_before_pickup (if set) must be greater than min
    Runs in addition to the model's own clean(), which only catches
    overlaps against rows already saved in the DB — this catches
    overlaps between rows being added in the same admin submission.
    """

    def clean(self):
        super().clean()

        by_mode: dict[str, list[tuple[int, int | None, int]]] = {}
        for idx, form in enumerate(self.forms):
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if form.cleaned_data.get("DELETE"):
                continue

            mode = form.cleaned_data.get("payment_mode")
            lo = form.cleaned_data.get("min_hours_before_pickup")
            hi = form.cleaned_data.get("max_hours_before_pickup")
            if mode is None or lo is None:
                continue

            if hi is not None and hi <= lo:
                form.add_error(
                    "max_hours_before_pickup",
                    "Must be greater than min_hours_before_pickup.",
                )
                continue

            by_mode.setdefault(mode, []).append((lo, hi, idx))

        for mode, ranges in by_mode.items():
            ranges.sort(key=lambda r: r[0])
            for i in range(len(ranges) - 1):
                lo, hi, _ = ranges[i]
                next_lo, _next_hi, next_idx = ranges[i + 1]
                if hi is None or next_lo < hi:
                    self.forms[next_idx].add_error(
                        "min_hours_before_pickup",
                        f"Overlaps another {mode} tier "
                        f"({lo}–{hi if hi is not None else '∞'} hrs).",
                    )


class CancellationTierInline(admin.TabularInline):
    model = CancellationTier
    formset = CancellationTierInlineFormSet
    extra = 1
    fields = (
        "payment_mode",
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
                )
            },
        ),
        (
            "Discount",
            {"fields": ("coupon_code", "discount_amount", "min_order_amount")},
        ),
        ("Validity", {"fields": ("valid_from", "valid_until")}),
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
        ("Linking", {"fields": ("city", "vehicle_type", "pickup_location")}),
        (
            "Card Overrides",
            {
                "fields": ("display_name", "display_price", "display_image", "tag"),
                "description": "All fields here are optional — each falls back to the linked VehicleType value when left blank.",
            },
        ),
        ("Ordering", {"fields": ("sort_order",)}),
    )


@admin.register(PlatformConfig)
class PlatformConfigAdmin(SoftDeleteAdmin):
    # summernote_fields = ("value",)
    list_display = ("key", "data_type", "created_at")
    list_filter = ("data_type",)
    search_fields = ("key", "description")
    readonly_fields = ("created_at", "last_updated_at")
    fieldsets = (
        (None, {"fields": ("key", "value", "description", "data_type")}),
        (
            "Meta",
            {
                "fields": ("created_at", "last_updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(LegalDocument)
class LegalDocumentAdmin(SummernoteModelAdmin):
    summernote_fields = ("content",)
    list_display = ("doc_type", "version", "is_current", "published_at", "created_at")
    list_filter = ("doc_type", "is_current")
    search_fields = ("doc_type",)
    readonly_fields = ("version", "created_at", "last_updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": ("doc_type", "version", "is_current", "content"),
            },
        ),
        (
            "Publishing",
            {
                "fields": ("published_at", "published_by"),
            },
        ),
        (
            "Meta",
            {
                "fields": ("created_at", "last_updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
