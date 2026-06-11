# apps/vehicles/urls.py

from django.urls import path
from apps.vehicles.views import VehicleDetailView, VehicleSearchView

urlpatterns = [
    path("search/", VehicleSearchView.as_view(), name="vehicle-search"),
    path("<int:listing_id>/", VehicleDetailView.as_view(), name="vehicle-detail"),
]
