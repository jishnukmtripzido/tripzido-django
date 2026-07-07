from django.core.management.base import BaseCommand
from apps.administrations.models import PlatformConfig


class Command(BaseCommand):
    help = "Seeds default PlatformConfig rows if they don't already exist."

    # Each entry: (key, value, description, data_type)
    DEFAULTS = [
        (
            "PENDING_BOOKING_EXPIRY_MINUTES",
            "15",
            "Minutes a PENDING_PAYMENT booking is held before it auto-expires.",
            "INTEGER",
        ),
        # Add more defaults here over time, e.g.:
        # ("OTP_EXPIRY_MINUTES", "5", "Minutes an OTP remains valid.", "INTEGER"),
        # ("MAX_RETRY_PAYMENT_ATTEMPTS", "3", "Max payment retry attempts allowed.", "INTEGER"),
    ]

    def handle(self, *args, **options):
        created_count = 0
        skipped_count = 0

        for key, value, description, data_type in self.DEFAULTS:
            obj, created = PlatformConfig.objects.get_or_create(
                key=key,
                defaults={
                    "value": value,
                    "description": description,
                    "data_type": data_type,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created: {key} = {value}"))
            else:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(f"Skipped (already exists): {key} = {obj.value}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Created {created_count}, skipped {skipped_count} (already present)."
            )
        )
