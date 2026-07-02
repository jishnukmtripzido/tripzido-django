from pathlib import Path
import requests
import environ
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Offer, PopularRental

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
