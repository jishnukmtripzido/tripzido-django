from django.contrib import admin

from apps.core.admin import SoftDeleteAdmin
from apps.vendors.models import (
    BankAccount,
    SubscriptionPlan,
    Vendor,
    VendorCommission,
    VendorDocument,
    VendorSubscription,
    VendorTerms,
)


@admin.register(VendorCommission)
class VendorCommissionAdmin(SoftDeleteAdmin):
    list_display = ("name", "commission_type", "flat_percentage", "is_deleted_display")
    search_fields = ("name",)
    readonly_fields = ("is_deleted_display",)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(SoftDeleteAdmin):
    list_display = (
        "name",
        "billing_cycle",
        "price",
        "is_default",
        "sort_order",
        "is_deleted_display",
    )
    list_filter = ("billing_cycle", "is_default")
    search_fields = ("name",)
    readonly_fields = ("is_deleted_display",)


@admin.register(Vendor)
class VendorAdmin(SoftDeleteAdmin):
    list_display = (
        "business_name",
        "owner_name",
        "email",
        "phone_number",
        "status",
        "is_deleted_display",
    )
    list_filter = ("status",)
    search_fields = ("business_name", "owner_name", "email", "phone_number")
    readonly_fields = (
        "is_deleted_display",
        "tc_updated_at",
        "reviewed_at",
        "suspended_at",
        "banned_at",
    )


@admin.register(VendorDocument)
class VendorDocumentAdmin(SoftDeleteAdmin):
    list_display = ("vendor", "doc_type", "status", "is_deleted_display")
    list_filter = ("doc_type", "status")
    search_fields = ("vendor__business_name",)
    readonly_fields = ("is_deleted_display", "reviewed_at")


@admin.register(BankAccount)
class BankAccountAdmin(SoftDeleteAdmin):
    list_display = (
        "vendor",
        "account_holder_name",
        "bank_name",
        "status",
        "is_active_acc",
        "is_deleted_display",
    )
    list_filter = ("status", "is_active_acc")
    search_fields = ("vendor__business_name", "account_holder_name", "account_number")
    readonly_fields = ("is_deleted_display", "submitted_at", "verified_at")


@admin.register(VendorSubscription)
class VendorSubscriptionAdmin(SoftDeleteAdmin):
    list_display = (
        "vendor",
        "plan",
        "status",
        "is_current",
        "amount_paid",
        "is_deleted_display",
    )
    list_filter = ("status", "is_current", "plan")
    search_fields = ("vendor__business_name", "plan__name")
    readonly_fields = ("is_deleted_display", "started_at", "expires_at", "cancelled_at")


@admin.register(VendorTerms)
class VendorTermsAdmin(SoftDeleteAdmin):
    list_display = (
        "vendor",
        "version",
        "is_current",
        "security_deposit_note",
        "operating_hours_note",
        "distance_limit_note",
        "excess_charge_note",
        "late_penalty_note",
    )
    list_filter = ("is_current",)
    search_fields = ("vendor__business_name",)
    readonly_fields = ("is_deleted_display", "version")
