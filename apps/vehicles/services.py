# apps/vehicles/services.py

from datetime import datetime
from django.core.exceptions import ValidationError
from apps.vehicles.repositories import VehicleSearchRepository


class VehicleSearchService:

    @staticmethod
    def search(city_id: int, pickup_datetime: datetime, dropoff_datetime: datetime):

        # Business rules
        now = datetime.now()
        if pickup_datetime < now:
            raise ValidationError("Pickup time cannot be in the past.")

        if dropoff_datetime <= pickup_datetime:
            raise ValidationError("Dropoff must be after pickup.")

        duration_hours = (dropoff_datetime - pickup_datetime).total_seconds() / 3600
        if duration_hours < 1:
            raise ValidationError("Minimum booking duration is 1 hour.")

        if duration_hours > 8760:  # 1 year
            raise ValidationError("Booking duration cannot exceed 1 year.")

        return VehicleSearchRepository.search(
            city_id=city_id,
            pickup_datetime=pickup_datetime,
            dropoff_datetime=dropoff_datetime,
        )