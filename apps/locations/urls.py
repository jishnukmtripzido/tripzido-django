# apps/locations/urls.py

from django.urls import path
from apps.locations.views import (
    CountryListCreateView,
    CountryDetailView,
    StateListCreateView,
    StateDetailView,
    CityListCreateView,
    CityDetailView,
    PickupLocationListCreateView,
    PickupLocationDetailView,
    PickupLocationsByCityView,
)

urlpatterns = [
    path("countries/", CountryListCreateView.as_view(), name="country-list"),
    path("countries/<int:pk>/", CountryDetailView.as_view(), name="country-detail"),
    path("states/", StateListCreateView.as_view(), name="state-list"),
    path("states/<int:pk>/", StateDetailView.as_view(), name="state-detail"),
    path("cities/", CityListCreateView.as_view(), name="city-list"),
    path("cities/<int:pk>/", CityDetailView.as_view(), name="city-detail"),
    path(
        "pickup-locations/by-city/<city_id>/",
        PickupLocationsByCityView.as_view(),
        name="pickup-locations-by-city",
    ),
    path(
        "pickup-locations/", PickupLocationListCreateView.as_view(), name="pickup-list"
    ),
    path(
        "pickup-locations/<int:pk>/",
        PickupLocationDetailView.as_view(),
        name="pickup-detail",
    ),
]
