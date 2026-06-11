from django.contrib import admin
from django.contrib import admin
from django.utils.html import format_html
from apps.core.admin import SoftDeleteAdmin
from apps.administrations.models import CancellationPolicy, CancellationTier


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
