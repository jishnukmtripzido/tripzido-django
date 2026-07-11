from django.urls import path
from apps.vendors.views import VendorTermsView

urlpatterns = [
    # path("countries/", CountryListCreateView.as_view(), name="country-list"),
    # apps/vendors/urls.py (add)
    path("<int:vendor_id>/terms/", VendorTermsView.as_view(), name="vendor-terms"),
]
