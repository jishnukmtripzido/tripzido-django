# apps/vehicles/urls.py

from django.urls import path
from apps.vehicles.views import VehicleSearchView

urlpatterns = [
    path("search/", VehicleSearchView.as_view(), name="vehicle-search"),
]