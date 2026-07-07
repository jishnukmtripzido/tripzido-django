from apps.administrations.models import (
    CancellationPolicy,
    Offer,
    PopularRental,
    AnnouncementBanner,
    LegalDocument,
    PlatformConfig,
)


class CancellationPolicyRepository:

    @staticmethod
    def get_current():
        return (
            CancellationPolicy.objects.filter(is_current=True)
            .prefetch_related("tiers")
            .first()
        )


class OfferRepository:

    @staticmethod
    def get_active_offers():
        """
        Returns all active Offer rows ordered by sort_order ascending.
        The first row is the featured (yellow) card.
        """
        return Offer.objects.filter(is_active=True).order_by("sort_order", "created_at")


class PopularRentalRepository:

    @staticmethod
    def get_active_by_city(city_id: int):
        """
        Returns active PopularRental rows for the given city, ordered by
        sort_order, with VehicleType pre-selected so the serializer never
        hits the DB again.
        """
        return (
            PopularRental.objects.filter(city_id=city_id, is_active=True)
            .select_related("vehicle_type", "city", "pickup_location")
            .order_by("sort_order", "created_at")
        )


class AnnouncementBannerRepository:
    @staticmethod
    def get_current_for_page(page: str):
        return AnnouncementBanner.objects.filter(
            page=page, is_current=True, is_active=True
        ).first()


class LegalDocumentRepository:

    @staticmethod
    def get_current(doc_type: str):
        return LegalDocument.objects.filter(doc_type=doc_type, is_current=True).first()


class PlatformConfigRepository:

    @staticmethod
    def get_by_key(key: str):
        return PlatformConfig.objects.filter(key=key).first()
