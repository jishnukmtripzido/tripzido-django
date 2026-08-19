from django.urls import path
from apps.payments.views import (
    AdminRefundDetailView,
    AdminRefundListView,
    AdminRefundStatusUpdateView,
    VendorPayoutsView,
    VendorPayoutDetailView,
    AdminEligibleBookingListView,
    AdminVendorPayoutListCreateView,
    AdminVendorPayoutDetailView,
    AdminVendorPayoutStatusUpdateView,
    AdminPaymentListView,
    AdminPaymentToggleReconciledView,
)

urlpatterns = [
    path("vendor/payouts/", VendorPayoutsView.as_view(), name="vendor-payouts"),
    path(
        "vendor/payouts/<int:payout_id>/",
        VendorPayoutDetailView.as_view(),
        name="vendor-payout-detail",
    ),
    path(
        "admin/eligible-bookings/",
        AdminEligibleBookingListView.as_view(),
        name="admin-eligible-bookings",
    ),
    path(
        "admin/payouts/",
        AdminVendorPayoutListCreateView.as_view(),
        name="admin-payouts",
    ),
    path(
        "admin/payouts/<int:payout_id>/",
        AdminVendorPayoutDetailView.as_view(),
        name="admin-payout-detail",
    ),
    path(
        "admin/payouts/<int:payout_id>/status/",
        AdminVendorPayoutStatusUpdateView.as_view(),
        name="admin-payout-status",
    ),
    path("admin/payments/", AdminPaymentListView.as_view(), name="admin-payments"),
    path(
        "admin/payments/<int:payment_id>/toggle-reconciled/",
        AdminPaymentToggleReconciledView.as_view(),
        name="admin-payment-toggle-reconciled",
    ),
    path("admin/refunds/", AdminRefundListView.as_view(), name="admin-refund-list"),
    path(
        "admin/refunds/<int:refund_id>/",
        AdminRefundDetailView.as_view(),
        name="admin-refund-detail",
    ),
    path(
        "admin/refunds/<int:refund_id>/status/",
        AdminRefundStatusUpdateView.as_view(),
        name="admin-refund-status",
    ),
]
