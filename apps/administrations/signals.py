from pathlib import Path
import requests
import environ
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import (
    Offer,
    PopularRental,
    AnnouncementBanner,
    CancellationPolicy,
    CancellationTier,
)

env = environ.Env()
BASE_DIR = Path(__file__).resolve().parent.parent.parent
environ.Env.read_env(BASE_DIR / ".env")


def _revalidate(endpoint: str):
    try:
        url = env("FRONTEND_BASE_URL")
        secret = env("REVALIDATE_SECRET")
        requests.post(
            f"{url}/api/revalidate/{endpoint}",
            headers={"x-revalidate-secret": secret},
            timeout=5,
        )
    except Exception as e:
        print(f"Failed to revalidate {endpoint}: {e}")


@receiver(post_save, sender=Offer)
@receiver(post_delete, sender=Offer)
def revalidate_offers(sender, instance, **kwargs):
    _revalidate("get-offers")


@receiver(post_save, sender=PopularRental)
@receiver(post_delete, sender=PopularRental)
def revalidate_popular_rentals(sender, instance, **kwargs):
    _revalidate("get-popular-rentals")


@receiver(post_save, sender=AnnouncementBanner)
@receiver(post_delete, sender=AnnouncementBanner)
def revalidate_announcement_banner(sender, instance, **kwargs):
    _revalidate("get-announcement-banner")


@receiver(post_save, sender=CancellationPolicy)
@receiver(post_delete, sender=CancellationPolicy)
def revalidate_cancellation_policy(sender, instance, **kwargs):
    _revalidate("get-cancellation-policy")


@receiver(post_save, sender=CancellationTier)
@receiver(post_delete, sender=CancellationTier)
def revalidate_cancellation_tier(sender, instance, **kwargs):
    _revalidate("get-cancellation-policy")
