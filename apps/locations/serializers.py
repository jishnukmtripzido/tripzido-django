# apps/locations/serializers.py

from rest_framework import serializers
from apps.locations.models import Country, State, City, PickupLocation


class CountrySerializer(serializers.ModelSerializer):
    name = serializers.CharField(
        max_length=100,
        trim_whitespace=True,
        error_messages={
            "required": "Country name is required.",
            "blank": "Country name may not be blank.",
            "max_length": "Country name must not exceed 100 characters.",
        },
    )
    code = serializers.CharField(
        max_length=3,
        min_length=1,
        trim_whitespace=True,
        error_messages={
            "required": "Country code is required.",
            "blank": "Country code may not be blank.",
            "max_length": "Country code must be exactly 3 characters (ISO 3166-1 alpha-3).",
            "min_length": "Country code must be exactly 1 characters (ISO 3166-1 alpha-3).",
        },
    )

    class Meta:
        model = Country
        fields = ["id", "name", "code"]

    def validate_name(self, value: str) -> str:
        """Normalize to title-case and enforce uniqueness."""
        value = value.strip().title()
        qs = Country.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"A country with the name '{value}' already exists."
            )
        return value

    def validate_code(self, value: str) -> str:
        """Normalize to uppercase, enforce alpha-only and uniqueness."""
        value = value.strip().upper()
        if not value.isalpha():
            raise serializers.ValidationError(
                "Country code must contain only alphabetic characters."
            )
        qs = Country.objects.filter(code__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"A country with the code '{value}' already exists."
            )
        return value


# ── State ────────────────────────────────────────────────────────────────────


class StateSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    name = serializers.CharField(
        max_length=40,
        trim_whitespace=True,
        error_messages={
            "required": "State name is required.",
            "blank": "State name may not be blank.",
            "max_length": "State name must not exceed 40 characters.",
        },
    )
    code = serializers.CharField(
        max_length=10,
        trim_whitespace=True,
        required=False,
        allow_blank=True,
        error_messages={
            "max_length": "State code must not exceed 10 characters.",
        },
    )
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        error_messages={
            "required": "Country is required.",
            "null": "Country may not be null.",
            "does_not_exist": "No country found with the given ID.",
            "incorrect_type": "Country ID must be an integer.",
        },
    )

    class Meta:
        model = State
        fields = ["id", "name", "code", "country", "country_name"]

    def validate_name(self, value: str) -> str:
        """Normalize to title-case."""
        return value.strip().title()

    def validate_code(self, value: str) -> str:
        """Normalize to uppercase; allow blank; reject non-alphanumeric."""
        value = value.strip().upper()
        if value and not value.isalnum():
            raise serializers.ValidationError(
                "State code must contain only alphanumeric characters."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        """Enforce unique_together = ('country', 'name') with a clear message."""
        country = attrs.get("country", getattr(self.instance, "country", None))
        name = attrs.get("name", getattr(self.instance, "name", None))

        qs = State.objects.filter(country=country, name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"name": f"A state named '{name}' already exists in this country."}
            )
        return attrs


# ── City ─────────────────────────────────────────────────────────────────────


class CitySerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="state.name", read_only=True)
    country_name = serializers.CharField(source="state.country.name", read_only=True)

    name = serializers.CharField(
        max_length=40,
        trim_whitespace=True,
        error_messages={
            "required": "City name is required.",
            "blank": "City name may not be blank.",
            "max_length": "City name must not exceed 40 characters.",
        },
    )
    state = serializers.PrimaryKeyRelatedField(
        queryset=State.objects.all(),
        error_messages={
            "required": "State is required.",
            "null": "State may not be null.",
            "does_not_exist": "No state found with the given ID.",
            "incorrect_type": "State ID must be an integer.",
        },
    )

    city_image = serializers.ImageField(
        required=False,
        allow_null=True,
        error_messages={
            "invalid_image": "Upload a valid image file.",
        },
    )

    class Meta:
        model = City
        fields = ["id", "name", "state", "state_name", "country_name", "city_image"]

    def validate_name(self, value: str) -> str:
        """Normalize to title-case."""
        return value.strip().title()

    def validate(self, attrs: dict) -> dict:
        """
        - Enforce state.country == country (mirrors City.clean()).
        - Enforce unique_together = ('name', 'state').
        """
        state = attrs.get("state", getattr(self.instance, "state", None))
        name = attrs.get("name", getattr(self.instance, "name", None))

        # unique_together: ('name', 'state')
        qs = City.objects.filter(name__iexact=name, state=state)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"name": f"A city named '{name}' already exists in this state."}
            )

        return attrs


# ── Pickup Location ───────────────────────────────────────────────────────────


class PickupLocationSerializer(serializers.ModelSerializer):
    city_name = serializers.CharField(source="city.name", read_only=True)

    name = serializers.CharField(
        max_length=200,
        trim_whitespace=True,
        error_messages={
            "required": "Pickup location name is required.",
            "blank": "Pickup location name may not be blank.",
            "max_length": "Pickup location name must not exceed 200 characters.",
        },
    )
    address = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    city = serializers.PrimaryKeyRelatedField(
        queryset=City.objects.all(),
        error_messages={
            "required": "City is required.",
            "null": "City may not be null.",
            "does_not_exist": "No city found with the given ID.",
            "incorrect_type": "City ID must be an integer.",
        },
    )
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
        error_messages={
            "max_digits": "Latitude must have at most 9 digits in total.",
            "max_decimal_places": "Latitude must have at most 6 decimal places.",
            "invalid": "Enter a valid latitude value.",
        },
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
        error_messages={
            "max_digits": "Longitude must have at most 9 digits in total.",
            "max_decimal_places": "Longitude must have at most 6 decimal places.",
            "invalid": "Enter a valid longitude value.",
        },
    )

    class Meta:
        model = PickupLocation
        fields = ["id", "name", "address", "latitude", "longitude", "city", "city_name"]

    def validate_name(self, value: str) -> str:
        """Collapse internal whitespace."""
        return " ".join(value.split())

    def validate_latitude(self, value):
        """Ensure latitude is in the WGS-84 range [-90, 90]."""
        if value is not None and not (-90 <= value <= 90):
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        """Ensure longitude is in the WGS-84 range [-180, 180]."""
        if value is not None and not (-180 <= value <= 180):
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value

    def validate(self, attrs: dict) -> dict:
        """
        - Enforce that latitude and longitude are both provided or both absent.
        - Enforce unique_together = ('city', 'name').
        """
        city = attrs.get("city", getattr(self.instance, "city", None))
        name = attrs.get("name", getattr(self.instance, "name", None))
        latitude = attrs.get("latitude", getattr(self.instance, "latitude", None))
        longitude = attrs.get("longitude", getattr(self.instance, "longitude", None))

        # Lat/lng must be supplied together
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError(
                {
                    "latitude": "Latitude and longitude must both be provided or both left empty."
                }
            )

        # unique_together: ('city', 'name')
        qs = PickupLocation.objects.filter(city=city, name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {
                    "name": f"A pickup location named '{name}' already exists in this city."
                }
            )

        return attrs
