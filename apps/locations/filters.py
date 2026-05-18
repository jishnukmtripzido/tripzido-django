# apps/locations/filters.py

import django_filters
from apps.locations.models import City, State, PickupLocation,Country




class CountryFilter(django_filters.FilterSet):
    """
    CountryFilter is a filter set for the Country model that allows filtering
    based on the 'name' field. It uses a case-insensitive containment lookup
    to match the provided value with the 'name' field of the Country model.
    Attributes:
        name (django_filters.CharFilter): A filter for the 'name' field of the
            Country model, using the 'icontains' lookup expression.
    Meta:
        model (Country): The model associated with this filter set.
        fields (list): A list of fields that can be filtered, which includes 'name'.
    """

    # range filters
    name = django_filters.CharFilter(field_name="name",lookup_expr="icontains")

    class Meta:
        model = Country
        fields = ["name"]
        

class CityFilter(django_filters.FilterSet):
    # exact filters
    country = django_filters.NumberFilter(field_name="country__id")
    state = django_filters.NumberFilter(field_name="state__id")

    # range filters
    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        model = City
        fields = ["country", "state", "name"]


class StateFilter(django_filters.FilterSet):
    country = django_filters.NumberFilter(field_name="country__id")
    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        model = State
        fields = ["country", "name"]


class PickupLocationFilter(django_filters.FilterSet):
    city = django_filters.NumberFilter(field_name="city__id")
    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        model = PickupLocation
        fields = ["city", "name"]