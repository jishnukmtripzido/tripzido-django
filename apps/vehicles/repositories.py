from django.db.models import Prefetch, Avg, Count, Sum, Max, Q
from django.db import transaction
from apps.vehicles.models import (
    VehicleImage,
    VehicleType,
    VehicleListing,
    PricingPackage,
    ListingBlockedPeriod,
    OperatingScheduleTemplate,
    TemplateScheduleDay,
    VehicleReview,
    PricingPackageType,
    VendorPickupPoint,
)
from apps.vendors.models import Vendor, VendorTerms, VendorSubscription
from django.utils import timezone
from datetime import datetime, time


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

        A null end_datetime means an indefinite block — treated as
        extending to +infinity, so it overlaps any requested range whose
        start is on/after the block's own start. Without the isnull
        branch, `end_datetime__gt=pickup_dt` evaluates to NULL (not True)
        in SQL for those rows and they'd be silently excluded.
        """
        rows = (
            ListingBlockedPeriod.objects.filter(
                listing_id__in=listing_ids,
                start_datetime__lt=dropoff_dt,
            )
            .filter(Q(end_datetime__isnull=True) | Q(end_datetime__gt=pickup_dt))
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
                    "vendor__vendor_terms",
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

    @staticmethod
    def get_listing_for_checkout(listing_id: int):
        """
        Same shape as get_listing_by_id, but with select_for_update() for
        use inside BookingCheckoutService.create_order's transaction, so
        two concurrent checkouts on the same listing can't both pass the
        capacity check. Kept as a separate method (rather than adding a
        for_update flag to get_listing_by_id) since locking is only ever
        wanted in the checkout path, never on read-only detail/search
        requests.
        """
        return (
            VehicleListing.objects.select_for_update()
            .filter(id=listing_id, status=VehicleListing.Status.APPROVED)
            .select_related("vendor")
            .prefetch_related(
                Prefetch(
                    "vendor__vendor_terms",
                    queryset=VendorTerms.objects.filter(is_current=True),
                    to_attr="current_terms_list",
                ),
                Prefetch(
                    "vendor__subscriptions",
                    queryset=VendorSubscription.objects.filter(
                        is_current=True, status=VendorSubscription.Status.ACTIVE
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


class VendorFleetRepository:

    @staticmethod
    def get_listings_for_vendor(vendor_id: int):
        """
        Returns ALL of a vendor's listings regardless of status
        (PENDING/APPROVED/PAUSED/SUSPENDED/REJECTED) — this is the
        vendor managing their own inventory on the Fleet screen, not
        the public search endpoint, so nothing should be hidden from
        the owner (contrast with VehicleSearchRepository, which only
        returns APPROVED listings from APPROVED vendors).
        """
        return (
            VehicleListing.objects.filter(vendor_id=vendor_id)
            .select_related("vehicle_type", "pickup_location", "pickup_point")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=VehicleImage.objects.order_by("sort_order"),
                )
            )
            .order_by("-created_at")
        )

    @staticmethod
    def get_listing_for_vendor(listing_id: int, vendor_id: int):
        """
        Fetches a single listing scoped to a specific vendor — the
        vendor_id filter is a hard security boundary, not just a
        convenience: without it, a vendor could view another vendor's
        listing purely by guessing IDs (IDOR). This can't reuse
        VehicleDetailRepository.get_listing_by_id, which only checks
        status=APPROVED (the public customer-facing rule), not
        ownership — a vendor needs to see their own PENDING/REJECTED/
        SUSPENDED listings too.
        """
        return (
            VehicleListing.objects.filter(id=listing_id, vendor_id=vendor_id)
            .select_related(
                "vehicle_type",
                "pickup_location__city",
                "schedule_template",
                "pickup_point",
            )
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=VehicleImage.objects.order_by("sort_order"),
                ),
                Prefetch(
                    "pricing_packages",
                    queryset=PricingPackage.objects.select_related(
                        "package_type__category"
                    ).order_by("package_type__sort_order"),
                ),
                Prefetch(
                    "schedule_template__days",
                    queryset=TemplateScheduleDay.objects.order_by("day_of_week"),
                    to_attr="ordered_days",
                ),
            )
            .first()
        )

    @staticmethod
    @transaction.atomic
    def create_listing(
        vendor,
        vehicle_type,
        pickup_location,
        pickup_point,
        schedule_template,
        listing_fields: dict,
        packages: list[dict],
    ) -> VehicleListing:
        listing = VehicleListing.objects.create(
            vendor=vendor,
            vehicle_type=vehicle_type,
            pickup_location=pickup_location,
            pickup_point=pickup_point,
            schedule_template=schedule_template,
            **listing_fields,
        )
        # duration_hours is deliberately sourced from package_type, not
        # taken as vendor input — every service that reads booking
        # duration (AvailabilityService, VendorListingDetailService)
        # already reads pkg.package_type.duration_hours, never
        # pkg.duration_hours directly. Populating it from the same
        # source keeps the field from silently diverging from what the
        # rest of the app actually treats as the source of truth.
        package_rows = [
            PricingPackage(
                listing=listing,
                package_type=p["package_type"],
                duration_hours=p["package_type"].duration_hours,
                price=p["price"],
                pay_at_pickup_enabled=p.get("pay_at_pickup_enabled", False),
                partial_payment_percentage=p.get("partial_payment_percentage"),
                km_limit=p.get("km_limit"),
            )
            for p in packages
        ]
        PricingPackage.objects.bulk_create(package_rows)
        return listing

    @staticmethod
    def add_images(
        listing: VehicleListing, files: list, uploaded_by
    ) -> list[VehicleImage]:
        """
        Appends new images after whatever's already attached — sort_order
        continues from the current max rather than restarting at 0, so
        repeated upload calls don't collide with existing photos. The
        first image ever attached to a listing is auto-marked
        is_primary; every image after that defaults to False. There's
        no "set primary" endpoint yet — if that's later deleted,
        VendorFleetListingSerializer.get_primary_image already falls
        back to the first image by sort_order, so nothing breaks, it
        just picks a new de facto primary silently.
        """
        existing_count = listing.images.count()
        max_sort_order = listing.images.aggregate(Max("sort_order"))["sort_order__max"]
        next_sort_order = (max_sort_order + 1) if max_sort_order is not None else 0

        rows = [
            VehicleImage(
                listing=listing,
                image=f,
                source=VehicleImage.ImageSource.VENDOR,
                sort_order=next_sort_order + i,
                is_primary=(existing_count == 0 and i == 0),
                uploaded_by=uploaded_by,
            )
            for i, f in enumerate(files)
        ]
        return VehicleImage.objects.bulk_create(rows)

    @staticmethod
    def delete_image(listing_id: int, vendor_id: int, image_id: int) -> bool:
        """
        Ownership enforced via listing__vendor_id in the same filter as
        the delete itself — a mismatched listing_id/image_id/vendor_id
        combination deletes nothing rather than needing a separate
        existence check first.
        """
        deleted, _ = VehicleImage.objects.filter(
            id=image_id, listing_id=listing_id, listing__vendor_id=vendor_id
        ).delete()
        return deleted > 0

    @staticmethod
    @transaction.atomic
    def update_listing(
        listing: VehicleListing,
        pickup_location,
        pickup_point,
        schedule_template,
        listing_fields: dict,
        packages: list[dict],
    ) -> VehicleListing:
        for field, value in listing_fields.items():
            setattr(listing, field, value)
        listing.pickup_location = pickup_location
        listing.pickup_point = pickup_point
        listing.schedule_template = schedule_template
        # Every edit sends the listing back for re-review — clears a
        # stale rejection message so the detail page doesn't show an
        # old REJECTED reason next to a listing that's freshly PENDING.
        listing.status = VehicleListing.Status.PENDING_APPROVAL
        listing.rejection_reason = ""
        listing.approved_by = None
        listing.approved_at = None
        listing.save()

        # Full replace — same strategy as create, matches the edit
        # form always submitting the complete current package list
        # rather than a partial diff.
        listing.pricing_packages.all().delete()
        package_rows = [
            PricingPackage(
                listing=listing,
                package_type=p["package_type"],
                duration_hours=p["package_type"].duration_hours,
                price=p["price"],
                pay_at_pickup_enabled=p.get("pay_at_pickup_enabled", False),
                partial_payment_percentage=p.get("partial_payment_percentage"),
                km_limit=p.get("km_limit"),
            )
            for p in packages
        ]
        PricingPackage.objects.bulk_create(package_rows)
        return listing


class VehicleTypeRepository:

    @staticmethod
    def search(query: str | None = None):
        """
        Returns the full catalog regardless of is_published — that flag
        gates customer search visibility, not whether a vendor may
        create a listing against it. Confirm this reading if it
        surfaces something unexpected in testing.
        """
        qs = VehicleType.objects.all().order_by("brand", "name")
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(brand__icontains=query))
        return qs

    @staticmethod
    def get_by_id(vehicle_type_id: int):
        return VehicleType.objects.filter(id=vehicle_type_id).first()


class PackageTypeRepository:

    @staticmethod
    def get_all():
        return PricingPackageType.objects.select_related("category").order_by(
            "sort_order", "name"
        )

    @staticmethod
    def get_by_ids(ids: list[int]) -> dict[int, "PricingPackageType"]:
        return {pt.id: pt for pt in PricingPackageType.objects.filter(id__in=ids)}


class ScheduleTemplateRepository:

    @staticmethod
    def get_for_vendor(vendor_id: int):
        return (
            OperatingScheduleTemplate.objects.filter(vendor_id=vendor_id)
            .annotate(listings_count=Count("listings", distinct=True))
            .prefetch_related(
                Prefetch(
                    "days",
                    queryset=TemplateScheduleDay.objects.order_by("day_of_week"),
                    to_attr="ordered_days",
                )
            )
            .order_by("name")
        )

    @staticmethod
    def get_detail_for_vendor(template_id: int, vendor_id: int):
        return (
            OperatingScheduleTemplate.objects.filter(
                id=template_id, vendor_id=vendor_id
            )
            .annotate(listings_count=Count("listings", distinct=True))
            .prefetch_related(
                Prefetch(
                    "days",
                    queryset=TemplateScheduleDay.objects.order_by("day_of_week"),
                    to_attr="ordered_days",
                )
            )
            .first()
        )

    @staticmethod
    @transaction.atomic
    def update_for_vendor(
        template_id: int, vendor_id: int, name: str, days_data: list[dict]
    ):
        template = OperatingScheduleTemplate.objects.filter(
            id=template_id, vendor_id=vendor_id
        ).first()
        if template is None:
            return None

        template.name = name
        template.save(update_fields=["name"])

        template.days.all().delete()
        days = [
            TemplateScheduleDay(
                template=template,
                day_of_week=d["day_of_week"],
                open_time=d.get("open_time") or time(7, 0),
                close_time=d.get("close_time") or time(19, 0),
                is_closed=d.get("is_closed", False),
            )
            for d in days_data
        ]
        TemplateScheduleDay.objects.bulk_create(days)
        template.ordered_days = sorted(days, key=lambda d: d.day_of_week)
        return template

    @staticmethod
    def delete_for_vendor(template_id: int, vendor_id: int) -> bool:
        deleted, _ = OperatingScheduleTemplate.objects.filter(
            id=template_id, vendor_id=vendor_id
        ).delete()
        return deleted > 0

    @staticmethod
    def get_owned_by_vendor(template_id: int, vendor_id: int):
        # Ownership check happens here, at the query itself — a
        # template_id belonging to a different vendor simply doesn't
        # match this filter and comes back None, same "don't leak via
        # ID guessing" principle as VendorFleetRepository.get_listing_for_vendor.
        return OperatingScheduleTemplate.objects.filter(
            id=template_id, vendor_id=vendor_id
        ).first()

    @staticmethod
    @transaction.atomic
    def create_for_vendor(vendor_id: int, name: str, days_data: list[dict]):
        template = OperatingScheduleTemplate.objects.create(
            vendor_id=vendor_id, name=name
        )
        days = [
            TemplateScheduleDay(
                template=template,
                day_of_week=d["day_of_week"],
                open_time=d.get("open_time") or time(7, 0),
                close_time=d.get("close_time") or time(19, 0),
                is_closed=d.get("is_closed", False),
            )
            for d in days_data
        ]
        TemplateScheduleDay.objects.bulk_create(days)
        # Attach in sorted order so the response serializer doesn't
        # need a second query to reload with the same prefetch shape
        # get_for_vendor uses.
        template.ordered_days = sorted(days, key=lambda d: d.day_of_week)
        return template


class VendorBlockedPeriodRepository:

    @staticmethod
    def get_for_vendor(vendor_id: int):
        return (
            ListingBlockedPeriod.objects.filter(listing__vendor_id=vendor_id)
            .select_related("listing__vehicle_type", "listing__pickup_location")
            .order_by("start_datetime")
        )

    @staticmethod
    def get_by_id_for_vendor(block_id: int, vendor_id: int):
        return (
            ListingBlockedPeriod.objects.filter(
                id=block_id, listing__vendor_id=vendor_id
            )
            .select_related("listing__vehicle_type", "listing__pickup_location")
            .first()
        )

    @staticmethod
    def create_block(
        listing: VehicleListing,
        count: int,
        start_datetime,
        end_datetime,
        reason: str,
        note: str,
    ) -> ListingBlockedPeriod:
        block = ListingBlockedPeriod(
            listing=listing,
            count=count,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            reason=reason,
            note=note,
        )
        # full_clean() runs the model's own clean() — order, count vs.
        # available_count, and the no-overlap rule — on top of the
        # future-date check the service layer already did before
        # reaching here.
        block.full_clean()
        block.save()
        return block

    @staticmethod
    def update_block(
        block: ListingBlockedPeriod,
        count: int,
        start_datetime,
        end_datetime,
        reason: str | None = None,
        note: str | None = None,
    ) -> ListingBlockedPeriod:
        block.count = count
        block.start_datetime = start_datetime
        block.end_datetime = end_datetime
        if reason is not None:
            block.reason = reason
        if note is not None:
            block.note = note
        block.full_clean()
        block.save()
        return block

    @staticmethod
    def delete_block(block_id: int, vendor_id: int) -> bool:
        """
        Ownership enforced in the same filter as the delete itself —
        same IDOR-safe pattern as VendorFleetRepository.delete_image.
        No date/status restriction: removing a block only loosens an
        availability constraint, it can never create an overlap or
        violate fleet capacity, so there's nothing to validate beyond
        ownership — unlike create/update, which both must guard against
        conflicts a delete simply cannot cause.
        """
        deleted, _ = ListingBlockedPeriod.objects.filter(
            id=block_id, listing__vendor_id=vendor_id
        ).delete()
        return deleted > 0


class VendorPickupPointRepository:

    @staticmethod
    def get_for_vendor(vendor_id: int, pickup_location_id: int | None = None):
        qs = VendorPickupPoint.objects.filter(vendor_id=vendor_id).select_related(
            "pickup_location"
        )
        if pickup_location_id is not None:
            qs = qs.filter(pickup_location_id=pickup_location_id)
        return qs

    @staticmethod
    def get_detail_for_vendor(point_id: int, vendor_id: int):
        return (
            VendorPickupPoint.objects.filter(id=point_id, vendor_id=vendor_id)
            .select_related("pickup_location")
            .first()
        )

    @staticmethod
    def get_owned_by_vendor(point_id: int, vendor_id: int):
        return VendorPickupPoint.objects.filter(
            id=point_id, vendor_id=vendor_id
        ).first()

    @staticmethod
    def create_for_vendor(vendor_id: int, data: dict) -> VendorPickupPoint:
        point = VendorPickupPoint(vendor_id=vendor_id, **data)
        point.full_clean()
        point.save()
        return point

    @staticmethod
    def update_for_vendor(point_id: int, vendor_id: int, data: dict):
        point = VendorPickupPoint.objects.filter(
            id=point_id, vendor_id=vendor_id
        ).first()
        if point is None:
            return None
        for field, value in data.items():
            setattr(point, field, value)
        point.full_clean()
        point.save()
        return point

    @staticmethod
    def delete_for_vendor(point_id: int, vendor_id: int) -> bool:
        deleted, _ = VendorPickupPoint.objects.filter(
            id=point_id, vendor_id=vendor_id
        ).delete()
        return deleted > 0
