# apps/vehicles/services.py

from datetime import datetime, timedelta
from apps.vehicles.repositories import VehicleSearchRepository, AvailabilityRepository


class AvailabilityService:

    @staticmethod
    def is_available(
        listing_id: int,
        pickup_dt: datetime,
        dropoff_dt: datetime,
    ) -> tuple[bool, str]:
        """
        Detailed single-listing check.
        Used at booking time to give specific rejection reasons.
        """
        # 1. One-off blocks
        if AvailabilityRepository.has_blocking_period(
            listing_id, pickup_dt, dropoff_dt
        ):
            return False, "Listing is blocked during this period"

        # 2. Recurring schedule
        schedule = AvailabilityRepository.get_listing_schedule(listing_id)

        current = pickup_dt
        while current.date() <= dropoff_dt.date():
            day = current.weekday()
            day_schedule = schedule.get(day)

            if day_schedule is None or day_schedule.is_closed:
                return False, f"Listing is closed on {current.strftime('%A')}s"

            if current.date() == pickup_dt.date():
                if pickup_dt.time() < day_schedule.open_time:
                    return False, "Pickup time is before opening hours"
                if pickup_dt.time() >= day_schedule.close_time:
                    return False, "Pickup time is after closing hours"

            if current.date() == dropoff_dt.date():
                if dropoff_dt.time() > day_schedule.close_time:
                    return False, "Dropoff time is after closing hours"

            current += timedelta(days=1)

        return True, ""

    @staticmethod
    def filter_available_listing_ids(
        listing_ids: list[int],
        pickup_dt: datetime,
        dropoff_dt: datetime,
    ) -> list[int]:
        """
        Bulk availability filter for search results.
        Runs 3 DB queries regardless of listing count.
        """
        if not listing_ids:
            return []

        # 1. One-off blocks
        blocked_ids = AvailabilityRepository.get_blocked_listing_ids(
            listing_ids, pickup_dt, dropoff_dt
        )

        # 2. Build set of weekdays touched by this booking range
        required_days = set()
        current = pickup_dt
        while current.date() <= dropoff_dt.date():
            required_days.add(current.weekday())
            current += timedelta(days=1)

        # 3. Explicitly closed on a required day
        schedule_blocked_ids = AvailabilityRepository.get_schedule_blocked_listing_ids(
            listing_ids, required_days
        )

        # 4. No schedule entry at all for a required day = implicitly closed
        has_schedule_ids = AvailabilityRepository.get_scheduled_listing_ids(
            listing_ids, required_days
        )
        no_schedule_ids = set(listing_ids) - has_schedule_ids

        unavailable = blocked_ids | schedule_blocked_ids | no_schedule_ids
        return [lid for lid in listing_ids if lid not in unavailable]


class VehicleSearchService:

    @staticmethod
    def search(city_id: int, pickup_datetime: datetime, dropoff_datetime: datetime):
        # 1. Get candidate IDs (approved listings in city)
        candidate_ids = VehicleSearchRepository.get_candidate_listing_ids(city_id)

        # 2. Filter by availability (business logic lives here)
        available_ids = AvailabilityService.filter_available_listing_ids(
            listing_ids=candidate_ids,
            pickup_dt=pickup_datetime,
            dropoff_dt=dropoff_datetime,
        )

        # 3. Fetch full data for available listings
        active_listings = VehicleSearchRepository.get_listings_by_ids(available_ids)

        # 4. Group under VehicleTypes
        return VehicleSearchRepository.get_vehicle_types_for_listings(active_listings)
