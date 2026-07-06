from pathlib import Path
import requests
import environ
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.vehicles.models import (
    VehicleListing,
    TemplateScheduleDay,
)

env = environ.Env()
BASE_DIR = Path(__file__).resolve().parent.parent.parent
environ.Env.read_env(BASE_DIR / ".env")


def _revalidate_location_timing(listing_id: int):
    try:
        url = env("FRONTEND_BASE_URL")
        secret = env("REVALIDATE_SECRET")
        requests.post(
            f"{url}/api/revalidate/get-location-timing",
            json={"listing_id": listing_id},
            headers={"x-revalidate-secret": secret},
            timeout=5,
        )
    except Exception as e:
        print(f"Failed to revalidate location-timing for listing {listing_id}: {e}")


@receiver(post_save, sender=VehicleListing)
def revalidate_location_timing_on_listing_change(sender, instance, **kwargs):
    # Covers a listing being assigned a new (or removed) schedule_template.
    _revalidate_location_timing(instance.pk)


@receiver(post_save, sender=TemplateScheduleDay)
@receiver(post_delete, sender=TemplateScheduleDay)
def revalidate_location_timing_on_day_change(sender, instance, **kwargs):
    # A day entry belongs to a template, which can be shared across
    # many listings — revalidate all of them, not just one.
    affected_ids = VehicleListing.objects.filter(
        schedule_template_id=instance.template_id
    ).values_list("id", flat=True)
    for listing_id in affected_ids:
        _revalidate_location_timing(listing_id)
