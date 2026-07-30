from django.contrib import admin
from django.utils import timezone

from apps.payments.models import Payment, VendorPayout, VendorPayoutItem
from apps.bookings.models import Booking
from apps.core.admin import SoftDeleteAdmin

# Register your models here.


@admin.register(Payment)
class PaymentAdmin(SoftDeleteAdmin):
    list_display = (
        "gateway_order_id",
        "payment_type",
        "amount",
        "status",
        "initiated_at",
    )


class VendorPayoutItemInline(admin.TabularInline):
    model = VendorPayoutItem
    extra = 0
    autocomplete_fields = ["booking"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "booking":
            # Only offers bookings that are actually eligible: FULL
            # payment mode, COMPLETED, and not already attached to
            # any other payout. Leaving `amount` blank on the inline
            # row lets VendorPayoutItem.save() auto-fill it from
            # booking.net_amount.
            kwargs["queryset"] = Booking.objects.filter(
                payment_mode=Booking.PaymentMode.FULL,
                status=Booking.Status.COMPLETED,
                payout_item__isnull=True,
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(VendorPayout)
class VendorPayoutAdmin(SoftDeleteAdmin):
    list_display = [
        "id",
        "vendor",
        "status",
        "total_amount",
        "utr_number",
        "paid_at",
        "is_deleted_display",
        "created_at",
    ]
    list_filter = ["status", "vendor"]
    search_fields = ["vendor__business_name", "utr_number"]
    readonly_fields = ["total_amount", "created_at"]
    inlines = [VendorPayoutItemInline]
    autocomplete_fields = ["vendor", "paid_by"]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Recompute the stored total after inline items are saved —
        # staff never have to calculate it by hand.
        form.instance.recompute_total()

    def save_model(self, request, obj, form, change):
        # Auto-stamp paid_by/paid_at the moment staff flips status to
        # PAID, if not already filled in manually.
        if obj.status == VendorPayout.Status.PAID:
            if not obj.paid_by:
                obj.paid_by = request.user
            if not obj.paid_at:
                obj.paid_at = timezone.now()
        super().save_model(request, obj, form, change)
