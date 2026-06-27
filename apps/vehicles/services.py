# apps/vehicles/services.py

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING
from apps.vehicles.repositories import (
    VehicleSearchRepository,
    AvailabilityRepository,
    VehicleDetailRepository,
)
from apps.vehicles.utils import format_duration


class AvailabilityService:

    @staticmethod
    def is_available(
        listing_id: int,
        pickup_dt: datetime,
        dropoff_dt: datetime,
    ) -> tuple[bool, str]:
        """
        Checks whether the listing's recurring weekly schedule is open
        for the pickup and dropoff days specifically — correct days
        present, not marked closed, pickup/dropoff times within
        open/close hours.

        Days strictly BETWEEN pickup and dropoff are NOT required to be
        open, and a missing schedule entry on one of those middle days
        does NOT block the booking either — a closed day (or a day with
        no schedule entry at all) in the middle of a multi-day trip
        doesn't matter, since the vehicle is already with the customer
        and no pickup/dropoff activity happens on that day. Only the
        pickup date and dropoff date themselves must be open and have a
        schedule entry.

        This is purely a "is the business open" check. It does NOT
        check fleet capacity — a listing can be open for business but
        have zero free units due to existing bookings or vendor
        maintenance blocks. That's answered separately by
        get_remaining_capacity, which combines overlapping bookings
        and blocked-period counts against the listing's fleet size.
        """
        schedule = AvailabilityRepository.get_listing_schedule(listing_id)

        current = pickup_dt
        while current.date() <= dropoff_dt.date():
            is_pickup_day = current.date() == pickup_dt.date()
            is_dropoff_day = current.date() == dropoff_dt.date()
            is_boundary_day = is_pickup_day or is_dropoff_day

            if is_boundary_day:
                day = current.weekday()
                day_schedule = schedule.get(day)

                if day_schedule is None or day_schedule.is_closed:
                    return False, f"Listing is closed on {current.strftime('%A')}s"

                if is_pickup_day:
                    if pickup_dt.time() < day_schedule.open_time:
                        return (
                            False,
                            f"Pickup time is before opening hours ({day_schedule.open_time.strftime('%I:%M %p')})",
                        )
                    if pickup_dt.time() > day_schedule.close_time:
                        return (
                            False,
                            f"Pickup time is after closing hours ({day_schedule.close_time.strftime('%I:%M %p')})",
                        )

                if is_dropoff_day:
                    if dropoff_dt.time() < day_schedule.open_time:
                        return (
                            False,
                            f"Dropoff time is before opening hours ({day_schedule.open_time.strftime('%I:%M %p')})",
                        )
                    if dropoff_dt.time() > day_schedule.close_time:
                        return (
                            False,
                            f"Dropoff time is after closing hours ({day_schedule.close_time.strftime('%I:%M %p')})",
                        )

            current += timedelta(days=1)

        return True, ""

    @staticmethod
    def filter_available_listing_ids(
        listing_ids: list[int],
        pickup_dt: datetime,
        dropoff_dt: datetime,
    ) -> list[int]:
        if not listing_ids:
            return []

        # Only the pickup day and dropoff day matter for the closed /
        # missing-schedule checks below. A closed day, or a day with no
        # schedule entry at all, strictly in between pickup and dropoff
        # does NOT block the listing — only the pickup day or dropoff
        # day being closed or missing a schedule entry does.
        boundary_days = {pickup_dt.weekday(), dropoff_dt.weekday()}

        schedule_blocked_ids = AvailabilityRepository.get_schedule_blocked_listing_ids(
            listing_ids, boundary_days
        )

        no_schedule_ids = AvailabilityRepository.get_listings_missing_schedule_days(
            listing_ids, boundary_days
        )

        # Capacity (fully booked / fully blocked for these dates) is
        # intentionally NOT filtered here. Sold-out listings should still
        # appear in search results — just marked unavailable and sorted
        # last, which VehicleSearchService.search already handles via its
        # post-processing capacity computation + sort. Only schedule-based
        # closures (wrong day, no template assigned) actually remove a
        # listing from results entirely.
        unavailable = schedule_blocked_ids | no_schedule_ids
        return [lid for lid in listing_ids if lid not in unavailable]

    @staticmethod
    def get_remaining_capacity(
        listing_available_count: int,
        listing_id: int,
        pickup_dt: datetime,
        dropoff_dt: datetime,
    ) -> int:
        """
        Total fleet size minus units already committed for this date
        range — combining active customer bookings AND vendor-created
        blocked periods (e.g. a scooter sent for maintenance), each
        counted by however many units they actually occupy.
        """
        booked_counts = AvailabilityRepository.get_booked_counts_for_listings(
            [listing_id], pickup_dt, dropoff_dt
        )
        blocked_counts = AvailabilityRepository.get_blocked_counts_for_listings(
            [listing_id], pickup_dt, dropoff_dt
        )
        committed = booked_counts.get(listing_id, 0) + blocked_counts.get(listing_id, 0)
        return max(0, listing_available_count - committed)

    @staticmethod
    def compute_duration_hours(pickup_dt: datetime, dropoff_dt: datetime) -> Decimal:
        """
        Decimal hour count built from the timedelta's integer components
        (not float division), so it lines up exactly with
        package_type.duration_hours for the % == 0 checks below — float
        division can leave tiny noise (e.g. 335.99999999998 instead of
        336) that would silently break that check.
        """
        diff = dropoff_dt - pickup_dt
        return (
            Decimal(diff.days * 24)
            + Decimal(diff.seconds) / Decimal(3600)
            + Decimal(diff.microseconds) / Decimal(3_600_000_000)
        ).quantize(Decimal("0.01"))

    @staticmethod
    def get_applicable_packages(
        packages: list,
        duration_hours: Decimal,
    ) -> list[tuple]:
        """
        Returns every package usable for the given duration, each paired
        with the multiplier needed to fully cover it:

          1. Any package whose duration_hours divides evenly into the
             searched duration (multiplier = duration / pkg_duration —
             an exact match is just the multiplier == 1 case of this).
          2. If none divide evenly, falls back to the Daily package alone,
             rounded UP to the nearest whole day so the full duration is
             covered.
          3. If there's no Daily package either, returns [].

        Results from (1) are sorted cheapest-total first.
        """
        candidates = []
        for p in packages:
            pkg_hours = p.package_type.duration_hours
            if pkg_hours > 0 and duration_hours % pkg_hours == 0:
                multiplier = duration_hours / pkg_hours
                candidates.append((p, multiplier))

        if candidates:
            candidates.sort(key=lambda c: c[0].price * c[1])
            return candidates

        daily = next(
            (p for p in packages if p.package_type.category.name.lower() == "daily"),
            None,
        )
        if daily:
            units = duration_hours / daily.package_type.duration_hours
            multiplier = units.to_integral_value(rounding=ROUND_CEILING)
            return [(daily, multiplier)]

        return []

    @staticmethod
    def pick_package_for_listings(
        listing_ids: list[int],
        duration_hours: Decimal,
    ) -> dict[int, tuple]:
        """
        For each listing, picks the single cheapest applicable package —
        used for search cards, which only have room for one package per
        listing. See get_applicable_packages for the matching rules.
        """
        packages = AvailabilityRepository.get_packages_for_listings(listing_ids)

        by_listing: dict[int, list] = {}
        for pkg in packages:
            by_listing.setdefault(pkg.listing_id, []).append(pkg)

        result = {}
        for listing_id, pkgs in by_listing.items():
            applicable = AvailabilityService.get_applicable_packages(
                pkgs, duration_hours
            )
            if applicable:
                result[listing_id] = applicable[0]

        return result


class VehicleSearchService:

    @staticmethod
    def search(
        city_id: int,
        pickup_datetime: datetime,
        dropoff_datetime: datetime,
        vehicle_type_id: int | None = None,
    ):
        candidate_ids = VehicleSearchRepository.get_candidate_listing_ids(
            city_id, vehicle_type_id=vehicle_type_id
        )

        available_ids = AvailabilityService.filter_available_listing_ids(
            listing_ids=candidate_ids,
            pickup_dt=pickup_datetime,
            dropoff_dt=dropoff_datetime,
        )

        if not available_ids:
            return []

        duration_hours = AvailabilityService.compute_duration_hours(
            pickup_datetime, dropoff_datetime
        )

        matched = AvailabilityService.pick_package_for_listings(
            available_ids, duration_hours
        )

        final_ids = [lid for lid in available_ids if lid in matched]

        active_listings = VehicleSearchRepository.get_listings_by_ids(final_ids)
        vehicle_types = list(
            VehicleSearchRepository.get_vehicle_types_for_listings(active_listings)
        )

        listings_by_id = {l.id: l for vt in vehicle_types for l in vt.city_listings}
        booked_counts = AvailabilityRepository.get_booked_counts_for_listings(
            list(listings_by_id.keys()), pickup_datetime, dropoff_datetime
        )
        blocked_counts = AvailabilityRepository.get_blocked_counts_for_listings(
            list(listings_by_id.keys()), pickup_datetime, dropoff_datetime
        )
        for listing_id, listing in listings_by_id.items():
            pkg, multiplier = matched[listing_id]
            listing.matched_package = pkg
            pkg.matched_multiplier = multiplier
            pkg.searched_duration_hours = duration_hours
            committed = booked_counts.get(listing_id, 0) + blocked_counts.get(
                listing_id, 0
            )
            # Overwrite with remaining-for-these-dates so the frontend's
            # "X available" badge and sold-out check reflect THIS
            # search, not the listing's static total fleet size.
            listing.available_count = max(0, listing.available_count - committed)

        # ── Split VehicleType objects by vendor ───────────────────────
        # The default grouping puts all vendors' listings for the same
        # vehicle model under one VehicleType object. We instead want
        # one VehicleType-like object per (vehicle_type, vendor) pair so
        # the frontend renders a separate card per vendor.
        #
        # We create lightweight proxy objects by copying the VehicleType
        # and attaching only the listings that belong to a single vendor.
        # The serializer (VehicleSearchResultSerializer) reads
        # vt.city_listings, so as long as we set that attribute the
        # existing serializer works without any changes.
        from copy import copy

        split_vehicle_types = []
        for vt in vehicle_types:
            # Group this VehicleType's listings by vendor_id.
            by_vendor: dict[int, list] = {}
            for listing in vt.city_listings:
                by_vendor.setdefault(listing.vendor_id, []).append(listing)

            for vendor_listings in by_vendor.values():
                vt_copy = copy(vt)
                vt_copy.city_listings = vendor_listings
                split_vehicle_types.append(vt_copy)

        # ── Sort: sold-out cards last, same as before ─────────────────
        for vt in split_vehicle_types:
            vt.city_listings.sort(key=lambda l: l.available_count <= 0)

        split_vehicle_types.sort(
            key=lambda vt: all(l.available_count <= 0 for l in vt.city_listings)
        )

        return split_vehicle_types


class VehicleDetailService:

    DEFAULT_TERMS = [
        "One Day will be considered from 9 am to 9 am.",
        "Documents Required: Aadhar Card and Driving License.",
        "One Original Govt Address Proof has to be submitted during pickup and will be returned during drop.",
        "Fuel Charges are not included in the security deposit or rent.",
    ]

    @staticmethod
    def _get_current_terms(listing):
        terms_list = getattr(listing, "current_terms_list", [])
        return terms_list[0] if terms_list else None

    @staticmethod
    def _build_terms_and_conditions(terms) -> list[str]:
        if terms and terms.terms_items:
            return [item.strip() for item in terms.terms_items if item.strip()]
        return VehicleDetailService.DEFAULT_TERMS

    @staticmethod
    def _build_policies(listing, terms, operating_hours: str) -> dict:
        return {
            "security_deposit": float(listing.security_deposit_amount),
            "distance_limit": (
                f"{listing.km_limit_per_day} km/day"
                if listing.km_limit_per_day
                else "No Limit"
            ),
            "late_penalty_per_hour": float(listing.late_return_penalty_per_hour or 0),
            "location_timings": (
                terms.operating_hours_note
                if terms and terms.operating_hours_note
                else operating_hours
            ),
            "excess_charge": (
                terms.excess_charge_note
                if terms and terms.excess_charge_note
                else (
                    f"₹{listing.excess_charge_per_km}/km"
                    if listing.excess_charge_per_km
                    else "N/A"
                )
            ),
        }

    @staticmethod
    def _build_operating_hours(listing) -> str:
        if listing.operating_hours_start and listing.operating_hours_end:

            def fmt(t):
                period = "AM" if t.hour < 12 else "PM"
                hour12 = t.hour % 12 or 12
                return f"{hour12}:{t.minute:02d} {period}"

            return f"{fmt(listing.operating_hours_start)} - {fmt(listing.operating_hours_end)}"
        return "9:00 AM - 5:00 PM"

    @staticmethod
    def _get_vendor_commission_info(vendor) -> tuple[float | None, bool]:
        """
        Returns (flat_percentage, can_enable_partial_payment) sourced from
        the vendor's current active subscription plan's commission.
        (None, False) if the vendor has no current active subscription, or
        the commission has no flat_percentage configured.
        """
        subscriptions = getattr(vendor, "current_subscription_list", [])
        subscription = subscriptions[0] if subscriptions else None
        if subscription is None:
            return None, False

        plan = subscription.plan
        commission = plan.commission
        percentage = (
            float(commission.flat_percentage)
            if commission.flat_percentage is not None
            else None
        )
        return percentage, plan.can_enable_partial_payment

    @staticmethod
    def _build_packages(
        applicable: list[tuple],
        selected_pkg,
        partial_payment_percentage: float | None,
    ) -> list[dict]:
        """
        applicable: list of (PricingPackage, multiplier) from
        AvailabilityService.get_applicable_packages.

        partial_payment_percentage is sourced from the vendor's subscription
        commission (see _get_vendor_commission_info), not from the package
        itself — it's the same value across every package in this list.
        """
        selected_id = selected_pkg.pk if selected_pkg else None
        result = []

        for pkg, multiplier in applicable:
            total_price = pkg.price * multiplier
            km_limit = pkg.km_limit
            total_km_limit_value = int(km_limit * multiplier) if km_limit else None
            result.append(
                {
                    "id": pkg.pk,
                    "name": pkg.package_type.name,
                    "category": pkg.package_type.category.name,
                    "duration_hours": pkg.package_type.duration_hours,
                    "price_per_day": pkg.price,
                    "total_price": total_price,
                    "km_limit": km_limit,
                    "total_km_limit": (
                        "No Distance Limit"
                        if not km_limit
                        else f"{total_km_limit_value} km included"
                    ),
                    "label": f"{pkg.package_type.name} (₹ {int(total_price)} total)",
                    "is_default": pkg.pk == selected_id,
                    "partial_payment_percentage": partial_payment_percentage,
                }
            )
        return result

    @staticmethod
    def _build_fare_details(rent_amount: Decimal, refundable_deposit) -> dict:
        """
        Commission is 0% for now, so the full rent is collected at pickup
        and nothing is taken as an advance.
        """
        rent_amount = float(rent_amount)
        return {
            "rent_amount": rent_amount,
            "total": rent_amount,
            "remaining_rent": rent_amount,
            "advance_payment": 0.0,
            "refundable_deposit": float(refundable_deposit),
        }

    @staticmethod
    def _absolute_url(request, image_field):
        if not image_field:
            return None
        url = image_field.url
        return request.build_absolute_uri(url) if request else url

    @staticmethod
    def get_vehicle_detail(listing_id: int, request=None) -> dict | None:
        listing = VehicleDetailRepository.get_listing_by_id(listing_id)
        if listing is None:
            return None

        vt = listing.vehicle_type
        location = listing.pickup_location
        terms = VehicleDetailService._get_current_terms(listing)
        operating_hours = VehicleDetailService._build_operating_hours(listing)

        images = listing.images.all()
        image_urls = [
            VehicleDetailService._absolute_url(request, img.image) for img in images
        ]
        primary_image = VehicleDetailService._absolute_url(request, vt.primary_image)

        # ── Duration-aware package matching ──────────────────────────
        all_packages = list(listing.pricing_packages.all())

        package_id_param = pickup_str = dropoff_str = None
        if request is not None:
            package_id_param = request.query_params.get("package_id")
            pickup_str = request.query_params.get("pickup_datetime")
            dropoff_str = request.query_params.get("dropoff_datetime")

        searched_duration = None
        is_available = True
        availability_message = None
        displayed_available_count = listing.available_count

        if listing.available_count <= 0:
            is_available = False
            availability_message = "This vehicle is sold out at this location"

        if pickup_str and dropoff_str:
            pickup_dt = datetime.fromisoformat(pickup_str)
            dropoff_dt = datetime.fromisoformat(dropoff_str)

            # Only run the schedule check if not already blocked by
            # having zero total fleet — that's true regardless of dates.
            if is_available:
                is_available, availability_message = AvailabilityService.is_available(
                    listing.pk, pickup_dt, dropoff_dt
                )

            if is_available:
                remaining = AvailabilityService.get_remaining_capacity(
                    listing.available_count, listing.pk, pickup_dt, dropoff_dt
                )
                displayed_available_count = remaining
                if remaining <= 0:
                    is_available = False
                    availability_message = "No vehicles available for these dates"

            duration_hours = AvailabilityService.compute_duration_hours(
                pickup_dt, dropoff_dt
            )
            applicable = AvailabilityService.get_applicable_packages(
                all_packages, duration_hours
            )
            searched_duration = format_duration(duration_hours)
        else:
            applicable = [(p, Decimal("1")) for p in all_packages]

        selected = None
        if package_id_param:
            try:
                package_id_int = int(package_id_param)
            except (TypeError, ValueError):
                package_id_int = None
            if package_id_int is not None:
                selected = next(
                    (pair for pair in applicable if pair[0].pk == package_id_int),
                    None,
                )
        if selected is None:
            selected = applicable[0] if applicable else None

        commission_percentage, partial_payment_allowed = (
            VehicleDetailService._get_vendor_commission_info(listing.vendor)
        )
        effective_partial_percentage = (
            commission_percentage if partial_payment_allowed else None
        )

        packages = VehicleDetailService._build_packages(
            applicable, selected[0] if selected else None, effective_partial_percentage
        )

        rent_amount = selected[0].price * selected[1] if selected else Decimal("0")
        fare_details = VehicleDetailService._build_fare_details(
            rent_amount, listing.security_deposit_amount
        )

        pay_at_pickup_enabled = any(pkg.pay_at_pickup_enabled for pkg in all_packages)

        return {
            "id": listing.pk,
            "vehicle_type_id": vt.pk,
            "name": vt.name,
            "make_year": vt.make_year,
            "transmission_type": vt.transmission_type,
            "fuel_type": vt.fuel_type,
            "seats": vt.seats,
            "cc": vt.cc,
            "mileage_kmpl": float(vt.mileage_kmpl) if vt.mileage_kmpl else None,
            "top_speed_kmph": vt.top_speed_kmph,
            "fuel_capacity_litres": (
                float(vt.fuel_capacity_litres) if vt.fuel_capacity_litres else None
            ),
            "kerb_weight_kg": float(vt.weight_kg) if vt.weight_kg else None,
            "km_limit_per_day": listing.km_limit_per_day,
            "images": image_urls,
            "primary_image": primary_image,
            "available_count": displayed_available_count,
            "packages": packages,
            "selected_package_id": selected[0].pk if selected else None,
            "searched_duration": searched_duration,
            "fare_details": fare_details,
            "pickup_location": {
                "id": location.pk,
                "location_name": location.name,
                "exact_address_revealed_after_booking": True,
                "operating_hours": operating_hours,
                "latitude": float(location.latitude) if location.latitude else None,
                "longitude": float(location.longitude) if location.longitude else None,
            },
            "policies": VehicleDetailService._build_policies(
                listing, terms, operating_hours
            ),
            "terms_and_conditions": VehicleDetailService._build_terms_and_conditions(
                terms
            ),
            "pay_at_pickup_enabled": pay_at_pickup_enabled,
            "is_available": is_available,
            "availability_message": None if is_available else availability_message,
        }

    @staticmethod
    def get_checkout_summary(
        listing_id: int,
        package_id: int,
        pickup_dt: datetime,
        dropoff_dt: datetime,
        request=None,
    ) -> tuple[dict | None, str | None]:
        """
        Returns (summary, None) on success, or (None, error_message) if the
        listing/package can't be booked for these dates.

        Pricing here is PER VEHICLE (quantity = 1). The frontend multiplies
        by however many vehicles the customer selects, since rent and
        deposit scale linearly with quantity and km_limit doesn't scale
        with quantity at all — it's a per-vehicle allowance already baked
        into total_km_limit.
        """
        listing = VehicleDetailRepository.get_listing_by_id(listing_id)
        if listing is None:
            return None, "Vehicle listing not found"

        if listing.available_count <= 0:
            return None, "This vehicle is sold out at this location"

        is_available, message = AvailabilityService.is_available(
            listing_id, pickup_dt, dropoff_dt
        )
        if not is_available:
            return None, message

        remaining_capacity = AvailabilityService.get_remaining_capacity(
            listing.available_count, listing_id, pickup_dt, dropoff_dt
        )
        if remaining_capacity <= 0:
            return None, "No vehicles available for these dates"

        all_packages = list(listing.pricing_packages.all())
        duration_hours = AvailabilityService.compute_duration_hours(
            pickup_dt, dropoff_dt
        )
        applicable = AvailabilityService.get_applicable_packages(
            all_packages, duration_hours
        )

        match = next((pair for pair in applicable if pair[0].pk == package_id), None)
        if match is None:
            return None, "Selected package is not valid for this booking duration"

        pkg, multiplier = match
        unit_rent_amount = pkg.price * multiplier

        commission_percentage, partial_allowed = (
            VehicleDetailService._get_vendor_commission_info(listing.vendor)
        )
        can_pay_partial = bool(
            pkg.pay_at_pickup_enabled
            and partial_allowed
            and commission_percentage is not None
        )
        partial_payment_percentage = commission_percentage if can_pay_partial else None

        vt = listing.vehicle_type
        location = listing.pickup_location
        terms = VehicleDetailService._get_current_terms(listing)
        operating_hours = VehicleDetailService._build_operating_hours(listing)
        policies = VehicleDetailService._build_policies(listing, terms, operating_hours)

        km_limit = pkg.km_limit
        total_km_limit = (
            "No Distance Limit"
            if not km_limit
            else f"{int(km_limit * multiplier)} km included"
        )

        return {
            "listing_id": listing.pk,
            "package_id": pkg.pk,
            "package_name": pkg.package_type.name,
            "vehicle_name": vt.name,
            "primary_image": VehicleDetailService._absolute_url(
                request, vt.primary_image
            ),
            "available_count": remaining_capacity,
            "unit_rent_amount": float(unit_rent_amount),
            "unit_refundable_deposit": float(listing.security_deposit_amount),
            "can_pay_partial": can_pay_partial,
            "partial_payment_percentage": partial_payment_percentage,
            "pickup_datetime": pickup_dt.isoformat(),
            "dropoff_datetime": dropoff_dt.isoformat(),
            "duration_label": format_duration(duration_hours),
            "pickup_location_name": location.name,
            "things_to_remember": {
                "km_limit": total_km_limit,
                "excess_charge": policies["excess_charge"],
                "location_timings": policies["location_timings"],
                "late_penalty_per_hour": policies["late_penalty_per_hour"],
            },
        }, None


class VehicleReviewService:

    @staticmethod
    def get_listing_reviews(listing_id: int) -> dict:
        from apps.vehicles.repositories import VehicleReviewRepository

        aggregates = VehicleReviewRepository.get_rating_aggregates(listing_id)
        average_rating = aggregates["average_rating"] or 0

        reviews_queryset = VehicleReviewRepository.get_approved_reviews(listing_id)

        return {
            "average_rating": round(float(average_rating), 1),
            "reviews_queryset": reviews_queryset,
        }
