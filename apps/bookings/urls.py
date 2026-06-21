from django.urls import path
from apps.bookings.views import (
    CreateBookingOrderView,
    BookingPaymentStatusView,
    CashfreeWebhookView,
    CustomerBookingsView,
    CustomerBookingDetailView,
    BookingCancellationPreviewView,
    CancelBookingView,
)

urlpatterns = [
    path("checkout/", CreateBookingOrderView.as_view(), name="booking-create-order"),
    path(
        "checkout/status/<str:order_id>/",
        BookingPaymentStatusView.as_view(),
        name="booking-payment-status",
    ),
    path("webhooks/cashfree/", CashfreeWebhookView.as_view(), name="cashfree-webhook"),
    path("", CustomerBookingsView.as_view(), name="customer-bookings"),
    path(
        "<int:booking_id>/",
        CustomerBookingDetailView.as_view(),
        name="customer-booking-detail",
    ),
    path(
        "<int:booking_id>/cancellation-preview/",
        BookingCancellationPreviewView.as_view(),
        name="booking-cancellation-preview",
    ),
    path(
        "<int:booking_id>/cancel/",
        CancelBookingView.as_view(),
        name="booking-cancel",
    ),
]
