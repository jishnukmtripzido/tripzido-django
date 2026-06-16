# apps/vehicles/services.py

from datetime import datetime, timedelta
from decimal import Decimal
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

    @staticmethod
    def pick_package_for_listings(
        listing_ids: list[int],
        duration_hours: Decimal,
    ) -> dict[int, "PricingPackage"]:
        """
        For each listing, picks exactly one PricingPackage:
          1. Exact duration_hours match (any category)
          2. Else the listing's Daily package
          3. Else listing is excluded (no entry in returned dict)
        """
        packages = AvailabilityRepository.get_packages_for_listings(listing_ids)

        by_listing: dict[int, list] = {}
        for pkg in packages:
            by_listing.setdefault(pkg.listing_id, []).append(pkg)

        result = {}
        for listing_id, pkgs in by_listing.items():
            exact = next(
                (p for p in pkgs if p.package_type.duration_hours == duration_hours),
                None,
            )
            if exact:
                result[listing_id] = exact
                continue

            daily = next(
                (p for p in pkgs if p.package_type.category.name.lower() == "daily"),
                None,
            )
            if daily:
                result[listing_id] = daily

        return result


class VehicleSearchService:

    @staticmethod
    def search(city_id: int, pickup_datetime: datetime, dropoff_datetime: datetime):
        candidate_ids = VehicleSearchRepository.get_candidate_listing_ids(city_id)

        available_ids = AvailabilityService.filter_available_listing_ids(
            listing_ids=candidate_ids,
            pickup_dt=pickup_datetime,
            dropoff_dt=dropoff_datetime,
        )

        if not available_ids:
            return []

        duration_hours = Decimal(
            str((dropoff_datetime - pickup_datetime).total_seconds() / 3600)
        )

        matched_packages = AvailabilityService.pick_package_for_listings(
            available_ids, duration_hours
        )

        # listings with no matching package (no exact + no daily) are dropped
        final_ids = [lid for lid in available_ids if lid in matched_packages]

        active_listings = VehicleSearchRepository.get_listings_by_ids(final_ids)

        vehicle_types = VehicleSearchRepository.get_vehicle_types_for_listings(
            active_listings
        )

        # attach the single matched package onto each listing so the
        # serializer's existing `pricing_packages = pkg.pricing_packages.all()`
        # only sees one item
        listings_by_id = {l.id: l for vt in vehicle_types for l in vt.city_listings}
        for listing_id, listing in listings_by_id.items():
            listing.matched_package = matched_packages[listing_id]

        return vehicle_types


class VehicleDetailService:

    # ── Fallbacks used only when vendor hasn't set terms yet ──────────
    DEFAULT_TERMS = [
        "One Day will be considered from 9 am to 9 am.",
        "Documents Required: Aadhar Card and Driving License.",
        "One Original Govt Address Proof has to be submitted during pickup and will be returned during drop.",
        "Fuel Charges are not included in the security deposit or rent.",
    ]

    @staticmethod
    def _get_current_terms(listing):
        """
        Returns the current VendorTerms for the listing, or None.
        current_terms_list is set by Prefetch(to_attr=...) in the repo.
        """
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
    def _build_fare_details(listing, request=None) -> dict:

        pickup_str = request.query_params.get("pickup_datetime")
        dropoff_str = request.query_params.get("dropoff_datetime")
        pickup = datetime.fromisoformat(pickup_str)
        dropoff = datetime.fromisoformat(dropoff_str)
        diff = dropoff - pickup

        # Extract days and hours
        total_seconds = int(diff.total_seconds())
        days = diff.days
        hours = (total_seconds % 86400) // 3600  # remaining hours after full days
        total_hours = int(diff.total_seconds() // 3600)  # total hours overall

        print(days)  # 1
        print(hours)  # 0
        print(total_hours)  # 24

        daily_price = None
        package_duration = 24
        for pkg in listing.pricing_packages.all():
            if pkg.package_type.category.name.lower() == "daily":
                daily_price = float(pkg.price)
                package_duration = float(pkg.package_type.duration_hours)
                break

        if daily_price is None:
            first = listing.pricing_packages.first()
            daily_price = float(first.price) if first else 0.0
            package_duration = float(first.package_type.duration_hours)

        rent_amount = daily_price * package_duration
        advance_pct = 0.20
        advance_payment = round(rent_amount * advance_pct, 2)
        remaining_rent = round(rent_amount - advance_payment, 2)

        return {
            "rent_amount": rent_amount,
            "total": rent_amount,
            "remaining_rent": remaining_rent,
            "advance_payment": advance_payment,
            "refundable_deposit": float(listing.security_deposit_amount),
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
    def _get_multiplication_factor_from_duration():
        return None

    @staticmethod
    def get_vehicle_detail(listing_id: int, request=None) -> dict | None:
        from apps.vehicles.repositories import VehicleDetailRepository

        listing = VehicleDetailRepository.get_listing_by_id(listing_id)
        if listing is None:
            return None

        vt = listing.vehicle_type
        location = listing.pickup_location
        terms = VehicleDetailService._get_current_terms(listing)
        operating_hours = VehicleDetailService._build_operating_hours(listing)

        # ── Images ────────────────────────────────────────────────────
        def absolute_url(image_field):
            if not image_field:
                return None
            url = image_field.url
            return request.build_absolute_uri(url) if request else url

        images = listing.images.all()
        image_urls = [absolute_url(img.image) for img in images]
        primary_image = absolute_url(vt.primary_image) if vt.primary_image else None

        # ── Packages ──────────────────────────────────────────────────
        packages = [
            {
                "id": pkg.pk,
                "name": pkg.package_type.name,
                "price_per_day": pkg.price,
                "label": f"{pkg.package_type.name} (₹ {int(pkg.price)} per Day)",
            }
            for pkg in listing.pricing_packages.all()
        ]

        pay_at_pickup_enabled = any(
            pkg.pay_at_pickup_enabled for pkg in listing.pricing_packages.all()
        )

        return {
            "id": listing.pk,
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
            "available_count": listing.available_count,
            "packages": packages,
            "fare_details": VehicleDetailService._build_fare_details(listing, request),
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
        }


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
