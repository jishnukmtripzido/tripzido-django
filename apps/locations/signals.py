# in your cities app, signals.py
from pathlib import Path

import requests
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import City

import environ

env = environ.Env()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

environ.Env.read_env(BASE_DIR / ".env")


@receiver(post_save, sender=City)
def revalidate_nextjs_cache(sender, instance, **kwargs):
    try:
        url = env("FRONTEND_BASE_URL")
        revalidate_secret = env("REVALIDATE_SECRET")
        requests.post(
            f"{url}/api/revalidate/get-cities/",
            headers={"x-revalidate-secret": revalidate_secret},
        )
    except Exception as e:
        print(f"Failed to revalidate cache: {e}")
