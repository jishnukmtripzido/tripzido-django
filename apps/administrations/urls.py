from django.urls import path
from apps.administrations.views import (
    CancellationPolicyView,
    OfferListView,
    PopularRentalListView,
)

urlpatterns = [
    path(
        "cancellation-policy/",
        CancellationPolicyView.as_view(),
        name="cancellation-policy",
    ),
    path("offers/", OfferListView.as_view(), name="offer-list"),
    path(
        "popular-rentals/", PopularRentalListView.as_view(), name="popular-rental-list"
    ),
]
