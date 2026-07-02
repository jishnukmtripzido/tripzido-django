from apps.administrations.repositories import (
    AnnouncementBannerRepository,
    CancellationPolicyRepository,
    OfferRepository,
    PopularRentalRepository,
)


class CancellationPolicyService:

    @staticmethod
    def _auto_label(min_h: int, max_h: int | None) -> str:
        if max_h is None:
            return f"More than {min_h} hours before pickup"
        if min_h == 0:
            return f"Less than {max_h} hours before pickup"
        return f"{min_h} – {max_h} hours before pickup"

    @staticmethod
    def _auto_description(refund: int) -> str:
        if refund == 100:
            return "Full refund of advance payment."
        if refund == 0:
            return "No refund."
        return f"{refund}% refund of advance payment."

    @staticmethod
    def get_current_policy() -> dict | None:
        policy = CancellationPolicyRepository.get_current()
        if policy is None:
            return None

        tiers = sorted(policy.tiers.all(), key=lambda t: -t.min_hours_before_pickup)

        rules = []
        for tier in tiers:
            min_h = tier.min_hours_before_pickup
            max_h = tier.max_hours_before_pickup
            refund = int(tier.refund_percentage)

            rules.append(
                {
                    "hours_before_pickup": min_h,
                    "refund_percentage": refund,
                    "label": tier.label
                    or CancellationPolicyService._auto_label(min_h, max_h),
                    "description": tier.description
                    or CancellationPolicyService._auto_description(refund),
                }
            )

        return {
            "rules": rules,
            "note": policy.refund_note,
        }


class OfferService:

    @staticmethod
    def get_offers() -> list:
        """
        Returns active offers with is_featured annotated on the first item
        (lowest sort_order). The serializer reads this boolean so the
        frontend knows which card gets the yellow styling.
        """
        offers = list(OfferRepository.get_active_offers())
        for idx, offer in enumerate(offers):
            offer.is_featured = idx == 0
        return offers


class PopularRentalService:

    @staticmethod
    def get_popular_rentals(city_id: int) -> list:
        """
        Returns active PopularRental objects for the given city with
        resolved_name and resolved_image annotated so the serializer
        never branches on optional override fields.
        """
        rentals = list(PopularRentalRepository.get_active_by_city(city_id))
        for rental in rentals:
            vt = rental.vehicle_type
            rental.resolved_name = rental.display_name or vt.name
            rental.resolved_image = rental.display_image or vt.primary_image or None
            rental.resolved_pickup_location = rental.pickup_location
        return rentals


class AnnouncementBannerService:
    @staticmethod
    def get_current_banner(page: str):
        return AnnouncementBannerRepository.get_current_for_page(page)
