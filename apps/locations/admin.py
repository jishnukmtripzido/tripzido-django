from django.contrib import admin

from apps.core.admin import SoftDeleteAdmin
from apps.locations.models import Country, State, City, PickupLocation


@admin.register(Country)
class CountryAdmin(SoftDeleteAdmin):
    list_display = ("name", "code", "is_deleted_display")
    search_fields = ("name", "code")
    readonly_fields = ("is_deleted_display",)


@admin.register(State)
class StateAdmin(SoftDeleteAdmin):
    list_display = ("name", "code", "country", "is_deleted_display")
    list_filter = ("country",)
    search_fields = ("name", "code")
    readonly_fields = ("is_deleted_display",)


@admin.register(City)
class CityAdmin(SoftDeleteAdmin):
    list_display = ("name", "state", "is_deleted_display")
    list_filter = ("state",)
    search_fields = ("name",)
    readonly_fields = ("is_deleted_display",)


@admin.register(PickupLocation)
class PickupLocationAdmin(SoftDeleteAdmin):
    list_display = ("name", "city", "address", "is_deleted_display")
    list_filter = ("city__state", "city")
    search_fields = ("name", "address", "city__name")
    readonly_fields = ("is_deleted_display",)
