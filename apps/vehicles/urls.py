# apps/vehicles/urls.py

from django.urls import path
from apps.vehicles.views import VehicleDetailView, VehicleSearchView, VehicleReviewsView

urlpatterns = [
    path("search/", VehicleSearchView.as_view(), name="vehicle-search"),
    path("<int:listing_id>/", VehicleDetailView.as_view(), name="vehicle-detail"),
    path(
        "<int:listing_id>/reviews/",
        VehicleReviewsView.as_view(),
        name="vehicle-listing-reviews",
    ),
]
