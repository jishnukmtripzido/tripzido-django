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
    AdminCountryListCreateView,
    AdminCountryDetailView,
    AdminStateListCreateView,
    AdminStateDetailView,
    AdminCityListCreateView,
    AdminCityDetailView,
    AdminPickupLocationListCreateView,
    AdminPickupLocationDetailView,
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
    path(
        "admin/countries/",
        AdminCountryListCreateView.as_view(),
        name="admin-country-list",
    ),
    path(
        "admin/countries/<int:country_id>/",
        AdminCountryDetailView.as_view(),
        name="admin-country-detail",
    ),
    path("admin/states/", AdminStateListCreateView.as_view(), name="admin-state-list"),
    path(
        "admin/states/<int:state_id>/",
        AdminStateDetailView.as_view(),
        name="admin-state-detail",
    ),
    path("admin/cities/", AdminCityListCreateView.as_view(), name="admin-city-list"),
    path(
        "admin/cities/<int:city_id>/",
        AdminCityDetailView.as_view(),
        name="admin-city-detail",
    ),
    path(
        "admin/pickup-locations/",
        AdminPickupLocationListCreateView.as_view(),
        name="admin-pickup-location-list",
    ),
    path(
        "admin/pickup-locations/<int:location_id>/",
        AdminPickupLocationDetailView.as_view(),
        name="admin-pickup-location-detail",
    ),
]
