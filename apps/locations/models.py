"""
geography/models.py

Defines the geographical hierarchy used across the platform:

    Country → State → City → PickupLocation

These models scope customer search, vendor listings, and admin data access.
"""

from django.db import models
from django.core.exceptions import ValidationError
from apps.core.models import BaseModel


class Country(BaseModel):
    """
    Represents a country where Tripzido operates.

    Attributes:
        name (str): Full country name; unique across the table.
        code (str): ISO 3166-1 alpha-3 country code (e.g. ``"IND"``); unique.
    """

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=3, unique=True)  # ISO 3166-1 alpha-3

    class Meta:  # pylint: disable=too-few-public-methods
        """Default ordering and display name for the admin."""

        ordering = ["name"]
        verbose_name_plural = "Countries"

    def __str__(self) -> str:
        """Return the country name."""
        return self.name


class State(BaseModel):
    """
    Represents a state or province within a :class:`Country`.

    Attributes:
        country (Country): The parent country (protected from deletion while
            states exist beneath it).
        name (str): State name; unique within the same country.
        code (str): Optional short state code (e.g. ``"MH"`` for Maharashtra).
    """

    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="states",
    )
    name = models.CharField(max_length=40)
    code = models.CharField(max_length=10, blank=True)  # e.g. "MH", "NSW"

    class Meta:  # pylint: disable=too-few-public-methods
        """Enforce uniqueness of state name per country and set ordering."""

        unique_together = ("country", "name")
        ordering = ["country", "name"]

    def __str__(self) -> str:
        """Return ``"<state name>, <country code>"``."""
        return f"{self.name}, {self.country.code}"


class City(BaseModel):
    """
    Represents an active city on the platform.

    Cities scope customer vehicle searches and vendor listings.  Both
    ``state`` and ``country`` are stored directly so queries can filter by
    either without joining through :class:`State`.

    Attributes:
        name (str): City name; unique within the same state.
        state (State): The parent state (protected from deletion while cities
            exist beneath it).
        country (Country): Denormalised country reference for efficient
            filtering (protected from deletion).
        city_image (ImageField | None): Optional hero image shown in the UI.
    """

    name = models.CharField(max_length=40)
    state = models.ForeignKey(
        State,
        on_delete=models.PROTECT,
        related_name="cities",
    )
    city_image = models.ImageField(upload_to="cities/", null=True, blank=True)

    class Meta:  # pylint: disable=too-few-public-methods
        """Enforce uniqueness of city name per state and set ordering."""

        unique_together = ("name", "state")
        ordering = ["state", "name"]
        verbose_name_plural = "Cities"

    def __str__(self) -> str:
        """Return ``"<city name>, <state>"``."""
        return f"{self.name}, {self.state}"


class PickupLocation(BaseModel):
    """
    Represents a physical pickup point within a :class:`City`.

    Vendors assign vehicles to pickup locations.  Latitude/longitude are
    stored for map display (US-C07, US-A11).

    Attributes:
        city (City): The city this location belongs to (protected from
            deletion while locations exist beneath it).
        name (str): Display name of the location (e.g. ``"Airport Terminal 2"``);
            unique within the same city.
        address (str): Optional full postal address.
        latitude (Decimal | None): WGS-84 latitude, up to six decimal places
            (~0.1 m precision).
        longitude (Decimal | None): WGS-84 longitude, up to six decimal places
            (~0.1 m precision).
    """

    city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        related_name="pickup_locations",
    )
    name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    class Meta:  # pylint: disable=too-few-public-methods
        """Enforce uniqueness of location name per city and set ordering."""

        unique_together = ("city", "name")
        ordering = ["city", "name"]

    def __str__(self) -> str:
        """Return ``"<location name> — <city>"``."""
        return f"{self.name} \u2014 {self.city}"
