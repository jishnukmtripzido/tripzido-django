from django.contrib import admin
from apps.payments.models import Payment
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
