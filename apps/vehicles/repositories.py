# apps/vehicles/repositories.py

from django.db.models import Q
from apps.vehicles.models import VehicleListing

class VehicleSearchRepository:

    @staticmethod
    def search(city_id: int, pickup_datetime, dropoff_datetime):
        return (
            VehicleListing.objects
            .select_related(
                "vehicle_type",
                "vendor",
                "pickup_location",
                "pickup_location__city",
            )
            .prefetch_related(
                "pricing_packages__package_type",
                "images",
            )
            .filter(
                status=VehicleListing.Status.APPROVED,
                pickup_location__city_id=city_id,
                vendor__status="APPROVED",
            )
        )