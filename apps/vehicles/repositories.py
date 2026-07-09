from django.db.models import Prefetch, Avg, Count, Sum
from apps.vehicles.models import (
    VehicleImage,
    VehicleType,
    VehicleListing,
    PricingPackage,
    ListingBlockedPeriod,
    OperatingScheduleTemplate,
    TemplateScheduleDay,
    VehicleReview,
)
from apps.vendors.models import Vendor, VendorTerms, VendorSubscription
from django.utils import timezone
from datetime import datetime


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
    def get_schedule_blocked_listing_ids(
        listing_ids: list[int],
        days_of_week: set[int],
    ) -> set[int]:
        """
        Returns listing IDs whose assigned schedule template marks any
        of the given days as is_closed=True.

        Callers should pass only the PICKUP and DROPOFF weekdays here,
        not every weekday spanned by the trip — a closed day strictly
        between pickup and dropoff should not block the listing, only
        the pickup day or dropoff day being closed should.

        Listings with no template assigned are NOT included here —
        they're caught entirely by get_listings_missing_schedule_days
        instead, since "no template" and "template missing a day" are
        the same underlying problem.
        """
        listing_to_template = dict(
            VehicleListing.objects.filter(
                id__in=listing_ids, schedule_template__isnull=False
            ).values_list("id", "schedule_template_id")
        )
        if not listing_to_template:
            return set()

        template_to_listings: dict[int, list[int]] = {}
        for listing_id, template_id in listing_to_template.items():
            template_to_listings.setdefault(template_id, []).append(listing_id)

        closed_template_ids = set(
            TemplateScheduleDay.objects.filter(
                template_id__in=template_to_listings.keys(),
                day_of_week__in=days_of_week,
                is_closed=True,
            ).values_list("template_id", flat=True)
        )

        blocked = set()
        for template_id in closed_template_ids:
            blocked.update(template_to_listings[template_id])
        return blocked

    @staticmethod
    def get_listings_missing_schedule_days(
        listing_ids: list[int],
        days_of_week: set[int],
    ) -> set[int]:
        """
        Returns listing IDs that either have no schedule template
        assigned at all, or whose template is missing an entry for at
        least one of the given days — both cases mean implicitly closed
        on that day.

        Callers should pass only the PICKUP and DROPOFF weekdays here,
        not every weekday spanned by the trip — a missing entry for a
        day strictly between pickup and dropoff should not block the
        listing, only a missing entry on the pickup day or dropoff day
        should.
        """
        listing_to_template = dict(
            VehicleListing.objects.filter(id__in=listing_ids).values_list(
                "id", "schedule_template_id"
            )
        )

        no_template_ids = {
            listing_id
            for listing_id, template_id in listing_to_template.items()
            if template_id is None
        }

        template_to_listings: dict[int, list[int]] = {}
        for listing_id, template_id in listing_to_template.items():
            if template_id is not None:
                template_to_listings.setdefault(template_id, []).append(listing_id)

        rows = TemplateScheduleDay.objects.filter(
            template_id__in=template_to_listings.keys(),
            day_of_week__in=days_of_week,
        ).values_list("template_id", "day_of_week")

        days_by_template: dict[int, set[int]] = {}
        for template_id, day in rows:
            days_by_template.setdefault(template_id, set()).add(day)

        missing = set(no_template_ids)
        for template_id, listings_for_template in template_to_listings.items():
            if not days_of_week.issubset(days_by_template.get(template_id, set())):
                missing.update(listings_for_template)

        return missing

    # @staticmethod
    # def get_listing_schedule(listing_id: int) -> dict:
    #     """
    #     Returns a dict of {day_of_week: TemplateScheduleDay} for a
    #     single listing, via whichever template it's assigned. Empty
    #     dict if no template is assigned — every day then reads as
    #     "no entry", i.e. closed, same as before.
    #     """
    #     template_id = (
    #         VehicleListing.objects.filter(id=listing_id)
    #         .values_list("schedule_template_id", flat=True)
    #         .first()
    #     )
    #     if template_id is None:
    #         return {}
    #     return {
    #         d.day_of_week: d
    #         for d in TemplateScheduleDay.objects.filter(template_id=template_id)
    #     }

    @staticmethod
    def get_schedule_by_template_id(schedule_template_id: int | None) -> dict:
        """
        Returns a dict of {day_of_week: TemplateScheduleDay} for the given
        schedule template. Empty dict if schedule_template_id is None (no
        template assigned) — every day then reads as "no entry", i.e.
        closed, same as before.

        Takes the template ID directly instead of a listing_id, since
        every caller already has the listing loaded in memory and can pass
        listing.schedule_template_id — this avoids a repeat query to look
        up something we already have.
        """
        if schedule_template_id is None:
            return {}
        return {
            d.day_of_week: d
            for d in TemplateScheduleDay.objects.filter(
                template_id=schedule_template_id
            )
        }

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

    @staticmethod
    def get_booked_counts_for_listings(
        listing_ids: list[int],
        pickup_dt,
        dropoff_dt,
    ) -> dict[int, int]:
        from apps.bookings.models import Booking

        candidates = (
            Booking.objects.filter(
                listing_id__in=listing_ids,
                dropoff_date__gte=pickup_dt.date(),
                pickup_date__lte=dropoff_dt.date(),
            )
            .exclude(
                status__in=[
                    Booking.Status.CANCELLED,
                    Booking.Status.PAYMENT_FAILED,
                    Booking.Status.EXPIRED,
                ]
            )
            .values_list(
                "listing_id",
                "pickup_date",
                "pickup_time",
                "dropoff_date",
                "dropoff_time",
            )
        )

        counts: dict[int, int] = {}
        for listing_id, p_date, p_time, d_date, d_time in candidates:
            booking_pickup = datetime.combine(p_date, p_time)
            booking_dropoff = datetime.combine(d_date, d_time)

            # FIX: Ensure timezone alignment before comparison
            if timezone.is_aware(pickup_dt) and timezone.is_naive(booking_pickup):
                # Uses your Django settings.TIME_ZONE to make the naive datetimes aware
                booking_pickup = timezone.make_aware(booking_pickup)
                booking_dropoff = timezone.make_aware(booking_dropoff)

            if booking_pickup < dropoff_dt and booking_dropoff > pickup_dt:
                counts[listing_id] = counts.get(listing_id, 0) + 1

        return counts

    @staticmethod
    def get_blocked_counts_for_listings(
        listing_ids: list[int],
        pickup_dt,
        dropoff_dt,
    ) -> dict[int, int]:
        """
        Returns {listing_id: total units taken out of service by
        overlapping ListingBlockedPeriod rows for this date range}.
        Sums `count` across all overlapping blocks for a listing.
        """
        rows = (
            ListingBlockedPeriod.objects.filter(
                listing_id__in=listing_ids,
                start_datetime__lt=dropoff_dt,
                end_datetime__gt=pickup_dt,
            )
            .values("listing_id")
            .annotate(total=Sum("count"))
        )
        return {row["listing_id"]: row["total"] for row in rows}

    @staticmethod
    def get_fully_committed_listing_ids(
        listing_ids: list[int],
        pickup_dt,
        dropoff_dt,
    ) -> set[int]:
        """
        Returns listing IDs where every unit in the fleet is already
        committed for this date range — either booked by a customer or
        taken out of service by a vendor block — leaving zero free.
        Used by search's bulk filter.
        """
        booked_counts = AvailabilityRepository.get_booked_counts_for_listings(
            listing_ids, pickup_dt, dropoff_dt
        )
        blocked_counts = AvailabilityRepository.get_blocked_counts_for_listings(
            listing_ids, pickup_dt, dropoff_dt
        )
        if not booked_counts and not blocked_counts:
            return set()

        committed: dict[int, int] = {}
        for listing_id, n in booked_counts.items():
            committed[listing_id] = committed.get(listing_id, 0) + n
        for listing_id, n in blocked_counts.items():
            committed[listing_id] = committed.get(listing_id, 0) + n

        fleet_sizes = dict(
            VehicleListing.objects.filter(id__in=committed.keys()).values_list(
                "id", "available_count"
            )
        )

        return {
            listing_id
            for listing_id, total in committed.items()
            if total >= fleet_sizes.get(listing_id, 0)
        }


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
                    to_attr="current_terms_list",
                ),
                Prefetch(
                    "vendor__subscriptions",
                    queryset=VendorSubscription.objects.filter(
                        is_current=True,
                        status=VendorSubscription.Status.ACTIVE,
                    ).select_related("plan__commission"),
                    to_attr="current_subscription_list",
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


class LocationTimingRepository:

    @staticmethod
    def get_schedule_for_listing(listing_id: int) -> tuple[bool, dict]:
        """
        Returns (has_template, days) for the listing's assigned
        schedule template.

        has_template=False means the listing has no schedule_template
        assigned at all — callers should treat this as "nothing to
        show", not as "closed every day". That distinction is the
        whole point of returning a bool instead of just an empty dict.
        """
        template_id = (
            VehicleListing.objects.filter(id=listing_id)
            .values_list("schedule_template_id", flat=True)
            .first()
        )
        if template_id is None:
            return False, {}

        days = {
            d.day_of_week: d
            for d in TemplateScheduleDay.objects.filter(template_id=template_id)
        }
        return True, days
