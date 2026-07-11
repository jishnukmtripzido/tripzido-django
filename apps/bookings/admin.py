from django.contrib import admin
from apps.bookings.models import Booking, BookingCancellation
from apps.core.admin import SoftDeleteAdmin


class BookingCancellationInline(admin.TabularInline):
    """
    Shows the cancellation record (if any) directly on the Booking page.
    Read-only and add-disabled: a BookingCancellation should only ever be
    created via CancellationService.cancel_booking(), which also flips
    the booking's status and runs inside a locked transaction — creating
    one by hand here would desync the booking from its own audit trail.
    """

    model = BookingCancellation
    extra = 0
    can_delete = False
    fields = (
        "cancelled_by",
        "cancelled_by_role",
        "reason_code",
        "reason_text",
        "policy_version",
        "hours_before_pickup_at_cancellation",
        "refund_percentage",
        "refundable_amount",
        "forfeited_amount",
        "created_at",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(SoftDeleteAdmin):
    list_display = (
        "booking_reference",
        "customer",
        "listing",
        "status",
        "payment_mode",
        "pickup_date",
        "dropoff_date",
        "advance_amount",
        "remaining_amount",
        "created_at",
    )
    list_filter = (
        "status",
        "payment_mode",
        "cancelled_by_role",
        "pickup_date",
        "dropoff_date",
    )
    search_fields = ("booking_reference",)
    date_hierarchy = "created_at"
    list_select_related = ("customer", "listing", "pickup_location")
    inlines = [BookingCancellationInline]

    # Pricing, T&C, and cancellation-policy fields are frozen snapshots
    # taken at checkout time — the whole point of freezing them (per the
    # model's own docstrings) is that they never change after the fact,
    # even if the live listing/policy/terms are edited later. Leaving
    # them editable in admin would let someone silently break that
    # guarantee, so they're locked to read-only here.
    readonly_fields = (
        "booking_group_id",
        "booking_reference",
        "price_snapshot",
        "commission_percentage",
        "listing_amount",
        "commission_amount",
        "discount_amount_on_commission",
        "net_commission_amount",
        "net_amount",
        "vendor_terms_snapshot",
        "platform_tc_snapshot",
        "cancellation_policy_snapshot",
        "created_at",
    )

    fieldsets = (
        (
            "Booking",
            {
                "fields": (
                    "booking_reference",
                    "booking_group_id",
                    "customer",
                    "listing",
                    "pickup_location",
                    "status",
                )
            },
        ),
        (
            "Schedule",
            {
                "fields": (
                    "pickup_date",
                    "pickup_time",
                    "dropoff_date",
                    "dropoff_time",
                    "expires_at",
                )
            },
        ),
        (
            "Pricing (frozen at checkout)",
            {
                "classes": ("collapse",),
                "fields": (
                    "pricing_package",
                    "price_snapshot",
                    "commission_percentage",
                    "listing_amount",
                    "commission_amount",
                    "discount_amount_on_commission",
                    "net_commission_amount",
                    "net_amount",
                    "security_deposit_amount",
                ),
            },
        ),
        (
            "Payment",
            {
                "fields": (
                    "payment_mode",
                    "advance_amount",
                    "remaining_amount",
                )
            },
        ),
        (
            "Terms & Conditions (frozen at checkout)",
            {
                "classes": ("collapse",),
                "fields": (
                    "platform_tc_document",
                    "platform_tc_snapshot",
                    "vendor_terms_version",
                    "vendor_terms_snapshot",
                    "tc_accepted_at",
                ),
            },
        ),
        (
            "Cancellation policy (frozen at checkout)",
            {
                "classes": ("collapse",),
                "fields": ("cancellation_policy_snapshot",),
            },
        ),
        (
            "Vendor operations",
            {
                "fields": (
                    "handed_over_at",
                    "handed_over_by",
                    "returned_at",
                    "return_confirmed_by",
                )
            },
        ),
        (
            "Cancellation",
            {
                "fields": (
                    "cancelled_at",
                    "cancelled_by_role",
                )
            },
        ),
        (
            "Metadata",
            {
                "classes": ("collapse",),
                "fields": ("created_at",),
            },
        ),
    )


@admin.register(BookingCancellation)
class BookingCancellationAdmin(SoftDeleteAdmin):
    """
    Read-only audit view. Creation happens exclusively through
    CancellationService.cancel_booking() (which also updates the parent
    Booking's status inside the same transaction), so manual add/delete
    here is disabled to avoid a cancellation record existing without a
    matching booking-state change, or vice versa.
    """

    list_display = (
        "booking",
        "cancelled_by_role",
        "reason_code",
        "refund_percentage",
        "refundable_amount",
        "forfeited_amount",
        "created_at",
    )
    list_filter = ("cancelled_by_role", "reason_code", "policy_version")
    search_fields = ("booking__booking_reference",)
    date_hierarchy = "created_at"
    list_select_related = ("booking", "cancelled_by")

    readonly_fields = (
        "booking",
        "cancelled_by",
        "cancelled_by_role",
        "reason_code",
        "reason_text",
        "policy_version",
        "hours_before_pickup_at_cancellation",
        "refund_percentage",
        "refundable_amount",
        "forfeited_amount",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
