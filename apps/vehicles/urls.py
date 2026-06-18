from django.urls import path
from apps.vehicles.views import (
    VehicleDetailView,
    VehicleSearchView,
    VehicleReviewsView,
    CheckoutSummaryView,
)

urlpatterns = [
    path("search/", VehicleSearchView.as_view(), name="vehicle-search"),
    path(
        "checkout-summary/",
        CheckoutSummaryView.as_view(),
        name="vehicle-checkout-summary",
    ),
    path("<int:listing_id>/", VehicleDetailView.as_view(), name="vehicle-detail"),
    path(
        "<int:listing_id>/reviews/",
        VehicleReviewsView.as_view(),
        name="vehicle-listing-reviews",
    ),
]
