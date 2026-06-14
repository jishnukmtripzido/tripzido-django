from django.contrib import admin
from apps.bookings.models import Booking
from apps.core.admin import SoftDeleteAdmin

# Register your models here.


@admin.register(Booking)
class PackageCategoryAdmin(SoftDeleteAdmin):
    list_display = ("booking_reference",)
