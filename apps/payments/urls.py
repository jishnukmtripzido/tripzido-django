from django.urls import path
from apps.payments.views import VendorPayoutsView, VendorPayoutDetailView

urlpatterns = [
    path("vendor/payouts/", VendorPayoutsView.as_view(), name="vendor-payouts"),
    path(
        "vendor/payouts/<int:payout_id>/",
        VendorPayoutDetailView.as_view(),
        name="vendor-payout-detail",
    ),
]
