# apps/vehicles/services.py

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING
from apps.vehicles.repositories import (
    VehicleSearchRepository,
    AvailabilityRepository,
    VehicleDetailRepository,
    LocationTimingRepository,
    VendorFleetRepository,
    VehicleTypeRepository,
    PackageTypeRepository,
    ScheduleTemplateRepository,
    VendorBlockedPeriodRepository,
    VendorPickupPointRepository,
)
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.locations.services import PickupLocationService
from django.utils import timezone
from apps.vehicles.utils import format_duration


class AvailabilityService:

    @staticmethod
    def is_available(
        schedule_template_id: int | None,
        pickup_dt: datetime,
        dropoff_dt: datetime,
    ) -> tuple[bool, str]:
        """
        Checks whether the listing's recurring weekly schedule is open
        for the pickup and dropoff days specifically — correct days
        present, not marked closed, pickup/dropoff times within
        open/close hours.

        Takes schedule_template_id (not listing_id) — callers already have
        the listing loaded, so this skips a repeat database lookup for
        something already in memory.

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
        schedule = AvailabilityRepository.get_schedule_by_template_id(
            schedule_template_id
        )

        current = pickup_dt
        while current.date() <= dropoff_dt.date():
            is_pickup_day = current.date() == pickup_dt.date()
            is_dropoff_day = current.date() == dropoff_dt.date()
            is_boundary_day = is_pickup_day or is_dropoff_day

            if is_boundary_day:
                day = current.weekday()
                day_schedule = schedule.get(day)

                if day_schedule is None or day_schedule.is_closed:
                    return False, f"Hub is closed on {current.strftime('%A')}s"

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
        """
        Returns listing IDs that should appear in search results.

        Hard-filters only listings with no template assigned or whose
        template is missing a day entry for the pickup or dropoff weekday —
        both mean the listing is misconfigured with no meaningful hours to
        show, so hiding them entirely is correct.

        Listings whose template explicitly marks the pickup or dropoff day
        as is_closed=True are NOT filtered out here. They pass through to
        search results with their real available_count intact, exactly like
        listings whose pickup/dropoff time falls outside open hours. The
        detail page catches them via AvailabilityService.is_available(),
        which returns is_available=False with a "Listing is closed on <Day>s"
        message — the same mechanism used for out-of-hours time selections.
        """
        if not listing_ids:
            return []

        # Only the pickup day and dropoff day matter for the closed /
        # missing-schedule checks below. A closed day, or a day with no
        # schedule entry at all, strictly in between pickup and dropoff
        # does NOT block the listing — only the pickup day or dropoff
        # day being closed or missing a schedule entry does.
        boundary_days = {pickup_dt.weekday(), dropoff_dt.weekday()}

        # Collected but not used for filtering — listings with is_closed=True
        # on the pickup/dropoff day are intentionally allowed through to search.
        # The detail page blocks booking for them via AvailabilityService.is_available().
        # _ = AvailabilityRepository.get_schedule_blocked_listing_ids(
        #     listing_ids, boundary_days
        # )

        no_schedule_ids = AvailabilityRepository.get_listings_missing_schedule_days(
            listing_ids, boundary_days
        )

        # Only hard-filter listings with no template / missing day entry.
        # Those are a vendor configuration problem with no meaningful hours
        # message to show, so removing them entirely is the right call.
        return [lid for lid in listing_ids if lid not in no_schedule_ids]

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
        # for vt in split_vehicle_types:
        #     vt.city_listings.sort(key=lambda l: l.available_count <= 0)

        # split_vehicle_types.sort(
        #     key=lambda vt: all(l.available_count <= 0 for l in vt.city_listings)
        # )

        # ── Sort listings within each card: cheapest-available first, sold-out last ──
        for vt in split_vehicle_types:
            vt.city_listings.sort(
                key=lambda l: (
                    l.available_count <= 0,
                    (
                        l.matched_package.price * l.matched_package.matched_multiplier
                        if l.available_count > 0
                        else Decimal("0")
                    ),
                )
            )

        # ── Sort cards: all-sold-out last, then cheapest-available-price first ──
        def _card_sort_key(vt):
            available = [l for l in vt.city_listings if l.available_count > 0]
            if not available:
                return (1, Decimal("0"))
            cheapest = min(
                l.matched_package.price * l.matched_package.matched_multiplier
                for l in available
            )
            return (0, cheapest)

        split_vehicle_types.sort(key=_card_sort_key)

        return split_vehicle_types


class VehicleDetailService:

    DEFAULT_TERMS = [
        "One Day will be considered from 9 am to 9 am.",
        "Documents Required: Aadhar Card and Driving License.",
        "One Original Govt Address Proof has to be submitted during pickup and will be returned during drop.",
        "Fuel Charges are not included in the security deposit or rent.",
    ]

    # @staticmethod
    # def _get_current_terms(listing):
    #     terms_list = getattr(listing, "current_terms_list", [])
    #     return terms_list[0] if terms_list else None
    @staticmethod
    def _get_current_terms(listing):
        terms_list = getattr(listing.vendor, "current_terms_list", [])
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
        availability_checked = False
        displayed_available_count = listing.available_count

        if listing.available_count <= 0:
            is_available = False
            availability_message = "This vehicle is sold out at this location"

        if pickup_str and dropoff_str:
            availability_checked = True
            pickup_dt = datetime.fromisoformat(pickup_str)
            dropoff_dt = datetime.fromisoformat(dropoff_str)

            # Only run the schedule check if not already blocked by
            # having zero total fleet — that's true regardless of dates.
            if is_available:
                is_available, availability_message = AvailabilityService.is_available(
                    listing.schedule_template_id, pickup_dt, dropoff_dt
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
        requested_package_unavailable = False
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
                    requested_package_unavailable = True
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
            "requested_package_unavailable": requested_package_unavailable,
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
            "availability_checked": availability_checked,
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
            listing.schedule_template_id, pickup_dt, dropoff_dt
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
        vendor_terms_items = VehicleDetailService._build_terms_and_conditions(terms)

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
            "vendor_id": listing.vendor.pk,  # NEW
            "vendor_name": listing.vendor.business_name,  # NEW
            "vendor_terms": vendor_terms_items,
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


class LocationTimingService:

    DAY_NAMES = {
        0: "Monday",
        1: "Tuesday",
        2: "Wednesday",
        3: "Thursday",
        4: "Friday",
        5: "Saturday",
        6: "Sunday",
    }

    @staticmethod
    def _format_time(t) -> str:
        period = "AM" if t.hour < 12 else "PM"
        hour12 = t.hour % 12 or 12
        return f"{hour12}:{t.minute:02d} {period}"

    @staticmethod
    def get_location_timing(listing_id: int) -> dict | None:
        """
        Returns None if the listing has no schedule_template assigned —
        the view turns that into a null `data` so the frontend knows to
        hide the section entirely.

        Otherwise returns all 7 days. A day with no TemplateScheduleDay
        row, or one explicitly marked is_closed=True, is reported as
        closed — same rule the availability check already uses.
        """

        has_template, days = LocationTimingRepository.get_schedule_for_listing(
            listing_id
        )
        if not has_template:
            return None

        result = []
        for day_of_week in range(7):
            day_schedule = days.get(day_of_week)
            if day_schedule is None or day_schedule.is_closed:
                result.append(
                    {
                        "day_of_week": day_of_week,
                        "day_name": LocationTimingService.DAY_NAMES[day_of_week],
                        "is_closed": True,
                        "timing": "Closed",
                    }
                )
            else:
                result.append(
                    {
                        "day_of_week": day_of_week,
                        "day_name": LocationTimingService.DAY_NAMES[day_of_week],
                        "is_closed": False,
                        "timing": (
                            f"{LocationTimingService._format_time(day_schedule.open_time)} - "
                            f"{LocationTimingService._format_time(day_schedule.close_time)}"
                        ),
                    }
                )

        return {"has_schedule": True, "days": result}


class VendorFleetService:

    @staticmethod
    def get_fleet_for_vendor(vendor_id: int):
        return VendorFleetRepository.get_listings_for_vendor(vendor_id)


class VendorListingDetailService:

    @staticmethod
    def _build_schedule(listing) -> dict:
        template = listing.schedule_template
        if template is None:
            return {
                "has_schedule": False,
                "id": None,
                "template_name": None,
                "days": [],
            }

        days_by_number = {
            d.day_of_week: d for d in getattr(template, "ordered_days", [])
        }
        days = []
        for day_of_week in range(7):
            day = days_by_number.get(day_of_week)
            if day is None or day.is_closed:
                days.append(
                    {
                        "day_of_week": day_of_week,
                        "day_name": LocationTimingService.DAY_NAMES[day_of_week],
                        "is_closed": True,
                        "open_time": None,
                        "close_time": None,
                        "timing": "Closed",
                    }
                )
            else:
                days.append(
                    {
                        "day_of_week": day_of_week,
                        "day_name": LocationTimingService.DAY_NAMES[day_of_week],
                        "is_closed": False,
                        "open_time": day.open_time.strftime("%H:%M"),
                        "close_time": day.close_time.strftime("%H:%M"),
                        "timing": (
                            f"{LocationTimingService._format_time(day.open_time)} - "
                            f"{LocationTimingService._format_time(day.close_time)}"
                        ),
                    }
                )
        # NEW: "id" added so the edit form can pre-select this template
        # in its dropdown — previously only the display name was returned.
        return {
            "has_schedule": True,
            "id": template.id,
            "template_name": template.name,
            "days": days,
        }

    @staticmethod
    def _absolute_url(request, image_field):
        if not image_field:
            return None
        url = image_field.url
        return request.build_absolute_uri(url) if request else url

    @staticmethod
    def get_detail(listing_id: int, vendor_id: int, request=None) -> dict | None:
        listing = VendorFleetRepository.get_listing_for_vendor(listing_id, vendor_id)
        if listing is None:
            return None

        vt = listing.vehicle_type
        location = listing.pickup_location

        images = [
            {
                "id": img.pk,
                "image_url": VendorListingDetailService._absolute_url(
                    request, img.image
                ),
                "is_primary": img.is_primary,
                "sort_order": img.sort_order,
            }
            for img in listing.images.all()
        ]

        packages = [
            {
                "id": pkg.pk,
                "package_type_id": pkg.package_type_id,  # NEW
                "name": pkg.package_type.name,
                "category": pkg.package_type.category.name,
                "duration_hours": pkg.package_type.duration_hours,
                "price": pkg.price,
                "pay_at_pickup_enabled": pkg.pay_at_pickup_enabled,
                "partial_payment_percentage": pkg.partial_payment_percentage,
                "km_limit": pkg.km_limit,
            }
            for pkg in listing.pricing_packages.all()
        ]

        return {
            "id": listing.pk,
            "status": listing.status,
            "rejection_reason": listing.rejection_reason,
            "available_count": listing.available_count,
            "vehicle_type": {
                "id": vt.pk,
                "name": vt.name,
                "brand": vt.brand,
                "make_year": vt.make_year,
                "transmission_type": vt.transmission_type,
                "fuel_type": vt.fuel_type,
                "vehicle_type": vt.vehicle_type,
                "seats": vt.seats,
                "cc": vt.cc,
                "mileage_kmpl": float(vt.mileage_kmpl) if vt.mileage_kmpl else None,
                "top_speed_kmph": vt.top_speed_kmph,
                "fuel_capacity_litres": (
                    float(vt.fuel_capacity_litres) if vt.fuel_capacity_litres else None
                ),
                "weight_kg": float(vt.weight_kg) if vt.weight_kg else None,
                "primary_image": VendorListingDetailService._absolute_url(
                    request, vt.primary_image
                ),
            },
            "pickup_location": {
                "id": location.pk,
                "name": location.name,
                "address": location.address,
                "city_id": location.city_id,
                "city_name": location.city.name,
                "latitude": float(location.latitude) if location.latitude else None,
                "longitude": float(location.longitude) if location.longitude else None,
            },
            "pickup_point": (
                {
                    "id": listing.pickup_point.id,
                    "label": listing.pickup_point.label,
                    "address": listing.pickup_point.address,
                    "contact_numbers": listing.pickup_point.contact_numbers,
                    "latitude": (
                        float(listing.pickup_point.latitude)
                        if listing.pickup_point.latitude
                        else None
                    ),
                    "longitude": (
                        float(listing.pickup_point.longitude)
                        if listing.pickup_point.longitude
                        else None
                    ),
                    "google_maps_link": listing.pickup_point.google_maps_link,
                }
                if listing.pickup_point
                else None
            ),
            "images": images,
            "pricing_packages": packages,
            "schedule": VendorListingDetailService._build_schedule(listing),
            "policies": {
                "security_deposit_amount": float(listing.security_deposit_amount),
                "km_limit_per_day": listing.km_limit_per_day,
                "excess_charge_per_km": (
                    float(listing.excess_charge_per_km)
                    if listing.excess_charge_per_km
                    else None
                ),
                "late_return_penalty_per_hour": (
                    float(listing.late_return_penalty_per_hour)
                    if listing.late_return_penalty_per_hour
                    else None
                ),
                "doorstep_delivery_enabled": listing.doorstep_delivery_enabled,
                "operating_hours_start": (
                    listing.operating_hours_start.strftime("%H:%M")
                    if listing.operating_hours_start
                    else None
                ),
                "operating_hours_end": (
                    listing.operating_hours_end.strftime("%H:%M")
                    if listing.operating_hours_end
                    else None
                ),
            },
            "created_at": listing.created_at,
        }


class VehicleTypeService:

    @staticmethod
    def search(query: str | None = None):
        return VehicleTypeRepository.search(query)


class PackageTypeService:

    @staticmethod
    def get_all():
        return PackageTypeRepository.get_all()


class ScheduleTemplateService:

    @staticmethod
    def get_for_vendor(vendor_id: int):
        return ScheduleTemplateRepository.get_for_vendor(vendor_id)

    @staticmethod
    def create_for_vendor(vendor_id: int, name: str, days_data: list[dict]):
        return ScheduleTemplateRepository.create_for_vendor(vendor_id, name, days_data)

    @staticmethod
    def get_detail_for_vendor(template_id: int, vendor_id: int):
        return ScheduleTemplateRepository.get_detail_for_vendor(template_id, vendor_id)

    @staticmethod
    def update_for_vendor(
        template_id: int, vendor_id: int, name: str, days_data: list[dict]
    ):
        return ScheduleTemplateRepository.update_for_vendor(
            template_id, vendor_id, name, days_data
        )

    @staticmethod
    def delete_for_vendor(template_id: int, vendor_id: int) -> bool:
        return ScheduleTemplateRepository.delete_for_vendor(template_id, vendor_id)


class VendorListingCreateService:

    @staticmethod
    @transaction.atomic
    def create_listing(vendor, validated_data: dict) -> VehicleListing:
        vehicle_type = VehicleTypeRepository.get_by_id(
            validated_data["vehicle_type_id"]
        )
        if vehicle_type is None:
            raise ValidationError({"vehicle_type_id": "Vehicle type not found."})

        try:
            pickup_location = PickupLocationService.get_by_id(
                validated_data["pickup_location_id"]
            )
        except ValidationError:
            raise ValidationError({"pickup_location_id": "Pickup location not found."})

        pickup_point = VendorPickupPointRepository.get_owned_by_vendor(
            validated_data["pickup_point_id"], vendor.id
        )
        if pickup_point is None:
            raise ValidationError(
                {"pickup_point_id": "Pickup point not found for this vendor."}
            )

        schedule_template = ScheduleTemplateRepository.get_owned_by_vendor(
            validated_data["schedule_template_id"], vendor.id
        )
        if schedule_template is None:
            raise ValidationError(
                {"schedule_template_id": "Schedule template not found for this vendor."}
            )

        pricing_input = validated_data["pricing_packages"]
        package_type_ids = [p["package_type_id"] for p in pricing_input]
        package_types = PackageTypeRepository.get_by_ids(package_type_ids)
        missing = set(package_type_ids) - set(package_types.keys())
        if missing:
            raise ValidationError(
                {"pricing_packages": f"Unknown package type id(s): {sorted(missing)}"}
            )

        packages = [
            {
                "package_type": package_types[p["package_type_id"]],
                "price": p["price"],
                "pay_at_pickup_enabled": p.get("pay_at_pickup_enabled", False),
                "partial_payment_percentage": p.get("partial_payment_percentage"),
                "km_limit": p.get("km_limit"),
            }
            for p in pricing_input
        ]

        listing_fields = {
            "available_count": validated_data.get("available_count", 1),
            "security_deposit_amount": validated_data.get("security_deposit_amount", 0),
            "km_limit_per_day": validated_data.get("km_limit_per_day"),
            "excess_charge_per_km": validated_data.get("excess_charge_per_km"),
            "late_return_penalty_per_hour": validated_data.get(
                "late_return_penalty_per_hour"
            ),
            "doorstep_delivery_enabled": validated_data.get(
                "doorstep_delivery_enabled", False
            ),
            "operating_hours_start": validated_data.get("operating_hours_start"),
            "operating_hours_end": validated_data.get("operating_hours_end"),
        }

        return VendorFleetRepository.create_listing(
            vendor,
            vehicle_type,
            pickup_location,
            pickup_point,
            schedule_template,
            listing_fields,
            packages,
        )


class VendorListingImageService:

    @staticmethod
    def add_images(listing_id: int, vendor_id: int, files: list, uploaded_by):
        listing = VendorFleetRepository.get_listing_for_vendor(listing_id, vendor_id)
        if listing is None:
            return None
        return VendorFleetRepository.add_images(listing, files, uploaded_by)

    @staticmethod
    def delete_image(listing_id: int, vendor_id: int, image_id: int) -> bool:
        return VendorFleetRepository.delete_image(listing_id, vendor_id, image_id)


class VendorListingUpdateService:

    @staticmethod
    @transaction.atomic
    def update_listing(listing_id: int, vendor, validated_data: dict):
        listing = VendorFleetRepository.get_listing_for_vendor(listing_id, vendor.id)
        if listing is None:
            return None

        try:
            pickup_location = PickupLocationService.get_by_id(
                validated_data["pickup_location_id"]
            )
        except ValidationError:
            raise ValidationError({"pickup_location_id": "Pickup location not found."})

        pickup_point = VendorPickupPointRepository.get_owned_by_vendor(
            validated_data["pickup_point_id"], vendor.id
        )
        if pickup_point is None:
            raise ValidationError(
                {"pickup_point_id": "Pickup point not found for this vendor."}
            )

        schedule_template = ScheduleTemplateRepository.get_owned_by_vendor(
            validated_data["schedule_template_id"], vendor.id
        )
        if schedule_template is None:
            raise ValidationError(
                {"schedule_template_id": "Schedule template not found for this vendor."}
            )

        pricing_input = validated_data["pricing_packages"]
        package_type_ids = [p["package_type_id"] for p in pricing_input]
        package_types = PackageTypeRepository.get_by_ids(package_type_ids)
        missing = set(package_type_ids) - set(package_types.keys())
        if missing:
            raise ValidationError(
                {"pricing_packages": f"Unknown package type id(s): {sorted(missing)}"}
            )

        packages = [
            {
                "package_type": package_types[p["package_type_id"]],
                "price": p["price"],
                "pay_at_pickup_enabled": p.get("pay_at_pickup_enabled", False),
                "partial_payment_percentage": p.get("partial_payment_percentage"),
                "km_limit": p.get("km_limit"),
            }
            for p in pricing_input
        ]

        listing_fields = {
            "available_count": validated_data.get("available_count", 1),
            "security_deposit_amount": validated_data.get("security_deposit_amount", 0),
            "km_limit_per_day": validated_data.get("km_limit_per_day"),
            "excess_charge_per_km": validated_data.get("excess_charge_per_km"),
            "late_return_penalty_per_hour": validated_data.get(
                "late_return_penalty_per_hour"
            ),
            "doorstep_delivery_enabled": validated_data.get(
                "doorstep_delivery_enabled", False
            ),
            "operating_hours_start": validated_data.get("operating_hours_start"),
            "operating_hours_end": validated_data.get("operating_hours_end"),
        }

        return VendorFleetRepository.update_listing(
            listing,
            pickup_location,
            schedule_template,
            listing_fields,
            packages,
            pickup_point,
        )


class VendorBlockedPeriodService:

    @staticmethod
    def get_for_vendor(vendor_id: int):
        return VendorBlockedPeriodRepository.get_for_vendor(vendor_id)

    @staticmethod
    def get_block_detail(block_id: int, vendor_id: int):
        return VendorBlockedPeriodRepository.get_by_id_for_vendor(block_id, vendor_id)

    @staticmethod
    def create_block(vendor_id: int, validated_data: dict):
        listing = VendorFleetRepository.get_listing_for_vendor(
            validated_data["listing_id"], vendor_id
        )
        if listing is None:
            raise ValidationError({"listing_id": "Listing not found for this vendor."})

        if validated_data["start_datetime"] <= timezone.now():
            raise ValidationError(
                {"start_datetime": "Start date/time must be in the future."}
            )

        return VendorBlockedPeriodRepository.create_block(
            listing=listing,
            count=validated_data["count"],
            start_datetime=validated_data["start_datetime"],
            end_datetime=validated_data.get("end_datetime"),  # None = indefinite
            reason=validated_data.get("reason", "OTHER"),
            note=validated_data.get("note", ""),
        )

    @staticmethod
    def update_block(block_id: int, vendor_id: int, validated_data: dict):
        """
        Returns the updated block, or None if not found/not owned by
        this vendor.

        end_datetime may be omitted/null in validated_data — that's
        how a vendor either creates or keeps an indefinite block. The
        "must be in the future" check only applies when a concrete
        end_datetime is actually being set; an indefinite block has no
        end to validate. Sending a concrete end_datetime on a
        previously-indefinite block is how a vendor closes it.
        """
        block = VendorBlockedPeriodRepository.get_by_id_for_vendor(block_id, vendor_id)
        if block is None:
            return None

        end_datetime = validated_data.get("end_datetime")
        if end_datetime is not None and end_datetime <= timezone.now():
            raise ValidationError(
                {
                    "end_datetime": "End date/time must be in the future to edit this block."
                }
            )

        return VendorBlockedPeriodRepository.update_block(
            block,
            count=validated_data["count"],
            start_datetime=validated_data["start_datetime"],
            end_datetime=end_datetime,
            reason=validated_data.get("reason"),
            note=validated_data.get("note"),
        )

    @staticmethod
    def delete_block(block_id: int, vendor_id: int) -> bool:
        return VendorBlockedPeriodRepository.delete_block(block_id, vendor_id)


class VendorPickupPointService:

    @staticmethod
    def get_for_vendor(vendor_id: int, pickup_location_id: int | None = None):
        return VendorPickupPointRepository.get_for_vendor(vendor_id, pickup_location_id)

    @staticmethod
    def get_detail_for_vendor(point_id: int, vendor_id: int):
        return VendorPickupPointRepository.get_detail_for_vendor(point_id, vendor_id)

    @staticmethod
    def create_for_vendor(vendor_id: int, data: dict):
        return VendorPickupPointRepository.create_for_vendor(vendor_id, data)

    @staticmethod
    def update_for_vendor(point_id: int, vendor_id: int, data: dict):
        return VendorPickupPointRepository.update_for_vendor(point_id, vendor_id, data)

    @staticmethod
    def delete_for_vendor(point_id: int, vendor_id: int) -> bool:
        return VendorPickupPointRepository.delete_for_vendor(point_id, vendor_id)
