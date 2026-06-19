from django.urls import path
from apps.bookings.views import (
    CreateBookingOrderView,
    BookingPaymentStatusView,
    CashfreeWebhookView,
)

urlpatterns = [
    path("checkout/", CreateBookingOrderView.as_view(), name="booking-create-order"),
    path(
        "checkout/status/<str:order_id>/",
        BookingPaymentStatusView.as_view(),
        name="booking-payment-status",
    ),
    path("webhooks/cashfree/", CashfreeWebhookView.as_view(), name="cashfree-webhook"),
]
