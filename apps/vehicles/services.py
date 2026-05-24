# apps/vehicles/services.py

from datetime import datetime
from django.core.exceptions import ValidationError
from apps.vehicles.repositories import VehicleSearchRepository


class VehicleSearchService:

    @staticmethod
    def search(city_id: int, pickup_datetime: datetime, dropoff_datetime: datetime):

        # Business rules
        return VehicleSearchRepository.search(
            city_id=city_id,
            pickup_datetime=pickup_datetime,
            dropoff_datetime=dropoff_datetime,
        )