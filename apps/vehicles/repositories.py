

from django.db.models import Prefetch
from apps.vehicles.models import (
    VehicleType, VehicleListing, PricingPackage,
       ListingBlockedPeriod, ListingOperatingSchedule,
)
from apps.vendors.models import Vendor



class VehicleSearchRepository:

    @staticmethod
    def get_candidate_listing_ids(city_id: int) -> list[int]:
        """Returns IDs of all approved listings in the given city."""
        return list(
            VehicleListing.objects.filter(
                status=VehicleListing.Status.APPROVED,
                pickup_location__city_id=city_id,
                vendor__status=Vendor.Status.APPROVED,
            ).values_list("id", flat=True)
        )

    @staticmethod
    def get_listings_by_ids(listing_ids: list[int]):
        """Fetches full listing data for the given IDs with all relations."""
        return VehicleListing.objects.filter(
            id__in=listing_ids
        ).select_related(
            "pickup_location__city",
            "vendor",
        ).prefetch_related(
            Prefetch(
                "pricing_packages",
                queryset=PricingPackage.objects.select_related(
                    "package_type__category"
                ).order_by("package_type__sort_order"),
            ),
            "images",
        )

    @staticmethod
    def get_vehicle_types_for_listings(active_listings):
        """Returns published VehicleTypes that have listings in the given queryset."""
        return (
            VehicleType.objects
            .filter(is_published=True, listings__in=active_listings)
            .distinct()
            .prefetch_related(
                Prefetch(
                    "listings",
                    queryset=active_listings,
                    to_attr="city_listings",
                ),
            )
            .order_by("brand", "name")
        )


class AvailabilityRepository:

    @staticmethod
    def get_blocked_listing_ids(
        listing_ids: list[int],
        pickup_dt,
        dropoff_dt,
    ) -> set[int]:
        """Returns listing IDs that have a one-off block overlapping the range."""
        return set(
            ListingBlockedPeriod.objects.filter(
                listing_id__in=listing_ids,
                start_datetime__lt=dropoff_dt,
                end_datetime__gt=pickup_dt,
            ).values_list("listing_id", flat=True)
        )

    @staticmethod
    def get_schedule_blocked_listing_ids(
        listing_ids: list[int],
        days_of_week: set[int],
    ) -> set[int]:
        """Returns listing IDs that are marked is_closed on any of the given days."""
        return set(
            ListingOperatingSchedule.objects.filter(
                listing_id__in=listing_ids,
                day_of_week__in=days_of_week,
                is_closed=True,
            ).values_list("listing_id", flat=True)
        )

    @staticmethod
    def get_scheduled_listing_ids(
        listing_ids: list[int],
        days_of_week: set[int],
    ) -> set[int]:
        """
        Returns listing IDs that have ANY schedule entry for the given days.
        Used to find listings with missing schedule entries (= implicitly closed).
        """
        return set(
            ListingOperatingSchedule.objects.filter(
                listing_id__in=listing_ids,
                day_of_week__in=days_of_week,
            ).values_list("listing_id", flat=True)
        )

    @staticmethod
    def get_listing_schedule(listing_id: int) -> dict:
        """
        Returns a dict of {day_of_week: ListingOperatingSchedule}
        for a single listing. Used in detailed is_available check.
        """
        return {
            s.day_of_week: s
            for s in ListingOperatingSchedule.objects.filter(listing_id=listing_id)
        }

    @staticmethod
    def has_blocking_period(listing_id: int, pickup_dt, dropoff_dt) -> bool:
        """Single-listing one-off block check. Used in booking validation."""
        return ListingBlockedPeriod.objects.filter(
            listing_id=listing_id,
            start_datetime__lt=dropoff_dt,
            end_datetime__gt=pickup_dt,
        ).exists()