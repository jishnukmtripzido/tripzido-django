from django.db.models import Prefetch
from apps.vehicles.models import (
    VehicleImage,
    VehicleType,
    VehicleListing,
    PricingPackage,
    ListingBlockedPeriod,
    ListingOperatingSchedule,
    VehicleReview,
)
from apps.vendors.models import Vendor, VendorTerms
from django.db.models import Avg, Count


class VehicleSearchRepository:

    @staticmethod
    def get_candidate_listing_ids(
        city_id: int, vehicle_type_id: int | None = None
    ) -> list[int]:
        """Returns IDs of all approved listings in the given city,
        optionally narrowed to a single vehicle type."""
        qs = VehicleListing.objects.filter(
            status=VehicleListing.Status.APPROVED,
            pickup_location__city_id=city_id,
            vendor__status=Vendor.Status.APPROVED,
        )
        if vehicle_type_id is not None:
            qs = qs.filter(vehicle_type_id=vehicle_type_id)
        return list(qs.values_list("id", flat=True))

    @staticmethod
    def get_listings_by_ids(listing_ids: list[int]):
        """Fetches full listing data for the given IDs with all relations."""
        return (
            VehicleListing.objects.filter(id__in=listing_ids)
            .select_related(
                "pickup_location__city",
                "vendor",
            )
            .prefetch_related(
                Prefetch(
                    "pricing_packages",
                    queryset=PricingPackage.objects.select_related(
                        "package_type__category"
                    ).order_by("package_type__sort_order"),
                ),
                "images",
            )
        )

    @staticmethod
    def get_vehicle_types_for_listings(active_listings):
        """Returns published VehicleTypes that have listings in the given queryset."""
        return (
            VehicleType.objects.filter(is_published=True, listings__in=active_listings)
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

    @staticmethod
    def get_packages_for_listings(listing_ids: list[int]):
        """
        Returns PricingPackage queryset for given listings, restricted to
        packages whose category is 'daily' OR whose package_type.duration_hours
        will be matched in Python (duration_hours is a Decimal, exact match
        is cheap enough to do here too, but we keep this broad and filter
        in the service to avoid float/decimal mismatches across DBs).
        """
        return (
            PricingPackage.objects.filter(listing_id__in=listing_ids)
            .select_related("package_type__category")
            .order_by("listing_id", "package_type__sort_order")
        )


class VehicleDetailRepository:

    @staticmethod
    def get_listing_by_id(listing_id: int):
        return (
            VehicleListing.objects.filter(
                id=listing_id,
                status=VehicleListing.Status.APPROVED,
            )
            .select_related(
                "vehicle_type",
                "pickup_location__city",
                "vendor",
            )
            .prefetch_related(
                Prefetch(
                    "pricing_packages",
                    queryset=PricingPackage.objects.select_related(
                        "package_type__category"
                    ).order_by("package_type__sort_order"),
                ),
                Prefetch(
                    "images",
                    queryset=VehicleImage.objects.order_by("sort_order"),
                ),
                Prefetch(
                    "vendor_terms",
                    queryset=VendorTerms.objects.filter(is_current=True),
                    to_attr="current_terms_list",  # gives us a plain list
                ),
            )
            .first()
        )


class VehicleReviewRepository:

    @staticmethod
    def get_rating_aggregates(listing_id: int) -> dict:
        """Average rating + count of approved reviews for a listing."""
        return VehicleReview.objects.filter(
            listing_id=listing_id,
            moderation_status=VehicleReview.ModerationStatus.APPROVED,
        ).aggregate(average_rating=Avg("rating"), total_count=Count("id"))

    @staticmethod
    def get_approved_reviews(listing_id: int, limit: int | None = None):
        """Approved reviews for a listing, most recent first."""
        queryset = (
            VehicleReview.objects.filter(
                listing_id=listing_id,
                moderation_status=VehicleReview.ModerationStatus.APPROVED,
            )
            .select_related("customer", "listing__vehicle_type")
            .order_by("-created_at")
        )
        if limit is not None:
            queryset = queryset[:limit]
        return queryset
