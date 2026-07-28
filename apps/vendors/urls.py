from django.urls import path
from apps.vendors.views import VendorTermsView, VendorTermsManageView

urlpatterns = [
    # Vendor's own terms — auth required, no vendor_id in URL.
    path("me/terms/", VendorTermsManageView.as_view(), name="vendor-terms-manage"),
    # Public read of a specific vendor's terms — used by the customer app.
    path("<int:vendor_id>/terms/", VendorTermsView.as_view(), name="vendor-terms"),
]
