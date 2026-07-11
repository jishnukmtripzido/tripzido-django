from apps.administrations.repositories import (
    AnnouncementBannerRepository,
    CancellationPolicyRepository,
    OfferRepository,
    PopularRentalRepository,
    PlatformConfigRepository,
)
from apps.administrations.models import CancellationTier
import json
from decimal import Decimal, InvalidOperation
from django.core.cache import cache
from apps.administrations.repositories import LegalDocumentRepository
from apps.administrations.models import LegalDocument


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
    def _build_rules(policy, payment_mode: str) -> list[dict]:
        tiers = sorted(
            (t for t in policy.tiers.all() if t.payment_mode == payment_mode),
            key=lambda t: -t.min_hours_before_pickup,
        )
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
        return rules

    @staticmethod
    def get_current_policy() -> dict | None:
        policy = CancellationPolicyRepository.get_current()
        if policy is None:
            return None

        return {
            "full_payment_rules": CancellationPolicyService._build_rules(
                policy, CancellationTier.PaymentMode.FULL
            ),
            "partial_payment_rules": CancellationPolicyService._build_rules(
                policy, CancellationTier.PaymentMode.PARTIAL
            ),
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


class PlatformConfigService:
    """
    Typed accessor for PlatformConfig. Every getter falls back to the
    given default if the key doesn't exist, or if the stored value
    can't be parsed as the requested type (e.g. an admin fat-fingers a
    non-numeric string into an INTEGER-typed key) — a bad config value
    should never take checkout down, it should just silently fall back.
    """

    @staticmethod
    def get_int(key: str, default: int) -> int:
        config = PlatformConfigRepository.get_by_key(key)
        if config is None:
            return default
        try:
            return int(config.value)
        except (TypeError, ValueError):
            return default

    # @staticmethod
    # def get_int(key: str, default: int) -> int:
    #     cache_key = f"platform_config:{key}"
    #     cached = cache.get(cache_key)
    #     if cached is not None:
    #         return cached
    #     config = PlatformConfigRepository.get_by_key(key)
    #     value = int(config.value) if config else default
    #     cache.set(
    #         cache_key, value, timeout=300
    #     )  # 5 min TTL — admin changes propagate within 5 min
    #     return value

    @staticmethod
    def get_decimal(key: str, default: Decimal) -> Decimal:
        config = PlatformConfigRepository.get_by_key(key)
        if config is None:
            return default
        try:
            return Decimal(config.value)
        except (TypeError, ValueError, InvalidOperation):
            return default

    @staticmethod
    def get_bool(key: str, default: bool) -> bool:
        config = PlatformConfigRepository.get_by_key(key)
        if config is None:
            return default
        return config.value.strip().lower() in ("true", "1", "yes")

    @staticmethod
    def get_str(key: str, default: str) -> str:
        config = PlatformConfigRepository.get_by_key(key)
        return config.value if config is not None else default

    @staticmethod
    def get_json(key: str, default):
        config = PlatformConfigRepository.get_by_key(key)
        if config is None:
            return default
        try:
            return json.loads(config.value)
        except (TypeError, ValueError):
            return default


class LegalDocumentService:

    @staticmethod
    def get_current(doc_type: str):
        return LegalDocumentRepository.get_current(doc_type)
