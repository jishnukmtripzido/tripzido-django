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


class VehicleDetailService:

    # ── Hardcoded terms (swap for a DB model later) ───────────────────
    TERMS_AND_CONDITIONS = [
        "One Day will be considered from 9 am to 9 am.",
        "Documents Required: Aadhar Card and Driving License.",
        "One Original Govt Address Proof has to be submitted during pickup and will be returned during drop.",
        "Fuel Charges are not included in the security deposit or rent.",
    ]

    @staticmethod
    def _build_fare_details(listing: VehicleListing) -> dict:
        """
        Hardcoded fare calculation — replace with real logic later.
        Mirrors the mock: 2-day daily package, 20% advance.
        """
        daily_price = None
        for pkg in listing.pricing_packages.all():
            if pkg.package_type.category.name.lower() == "daily":
                daily_price = float(pkg.price)
                break

        if daily_price is None:
            # Fall back to first package if no daily package exists
            first = listing.pricing_packages.first()
            daily_price = float(first.price) if first else 0.0

        rent_amount = daily_price * 2  # hardcoded 2-day stay
        advance_pct = 0.20  # 20% advance
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
    def _build_operating_hours(listing: VehicleListing) -> str:
        if listing.operating_hours_start and listing.operating_hours_end:

            def fmt(t):
                hour = t.hour
                minute = t.minute
                period = "AM" if hour < 12 else "PM"
                hour12 = hour % 12 or 12
                return f"{hour12}:{minute:02d} {period}"

            return f"{fmt(listing.operating_hours_start)} - {fmt(listing.operating_hours_end)}"
        return "9:00 AM - 10:00 PM"  # hardcoded fallback

    @staticmethod
    def get_vehicle_detail(listing_id: int, request=None) -> dict:
        from apps.vehicles.repositories import VehicleDetailRepository

        listing = VehicleDetailRepository.get_listing_by_id(listing_id)
        if listing is None:
            return None

        vt = listing.vehicle_type
        location = listing.pickup_location
        operating_hours = VehicleDetailService._build_operating_hours(listing)

        # ── Images ────────────────────────────────────────────────────
        def absolute_url(image_field):
            if not image_field:
                return None
            url = image_field.url
            if request:
                return request.build_absolute_uri(url)
            return url

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

        # ── Pay-at-pickup ─────────────────────────────────────────────
        pay_at_pickup_enabled = any(
            pkg.pay_at_pickup_enabled for pkg in listing.pricing_packages.all()
        )

        # ── Policies ──────────────────────────────────────────────────
        policies = {
            "security_deposit": float(listing.security_deposit_amount),
            "distance_limit": (
                f"{listing.km_limit_per_day} km/day"
                if listing.km_limit_per_day
                else "No Limit"
            ),
            "late_penalty_per_hour": float(listing.late_return_penalty_per_hour or 0),
            "location_timings": operating_hours,
            "excess_charge": (
                f"₹{listing.excess_charge_per_km}/km"
                if listing.excess_charge_per_km
                else "N/A"
            ),
        }

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
            "fare_details": VehicleDetailService._build_fare_details(listing),
            "pickup_location": {
                "id": location.pk,
                "location_name": location.name,
                "exact_address_revealed_after_booking": True,  # hardcoded for now
                "operating_hours": operating_hours,
                "latitude": float(location.latitude) if location.latitude else None,
                "longitude": float(location.longitude) if location.longitude else None,
            },
            "policies": policies,
            "terms_and_conditions": VehicleDetailService.TERMS_AND_CONDITIONS,
            "pay_at_pickup_enabled": pay_at_pickup_enabled,
        }
