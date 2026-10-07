from django.core.management.base import BaseCommand
from apps.vehicles.models import PackageCategory, PricingPackageType


class Command(BaseCommand):
    """
    Seeds the default pricing package categories and types vendors price
    their listings with. Without at least one package type no listing can
    be priced, so nothing ever shows up in search.

    The "Daily" category name is load-bearing: AvailabilityService falls
    back to the package whose category.name.lower() == "daily" when no
    package divides the searched duration evenly. Renaming it silently
    hides listings from search for odd durations.

    Idempotent — matched by name; existing rows are left untouched, so
    re-running never overwrites admin changes.
    """

    help = "Seeds default pricing package categories and types if they don't exist."

    # (name, description, sort_order)
    CATEGORIES = [
        ("Daily", "Charged per 24 hours.", 0),
        ("Weekly", "Charged per 7 days.", 1),
    ]

    # (name, category_name, duration_hours, description, sort_order)
    PACKAGE_TYPES = [
        ("Daily", "Daily", "24.00", "24-hour rental.", 0),
        ("Weekly", "Weekly", "168.00", "7-day rental.", 1),
    ]

    def handle(self, *args, **options):
        categories = {}
        for name, description, sort_order in self.CATEGORIES:
            category, created = PackageCategory.objects.get_or_create(
                name=name,
                defaults={"description": description, "sort_order": sort_order},
            )
            categories[name] = category
            self._report("PackageCategory", name, created)

        for name, category_name, hours, description, sort_order in self.PACKAGE_TYPES:
            _, created = PricingPackageType.objects.get_or_create(
                name=name,
                defaults={
                    "category": categories[category_name],
                    "duration_hours": hours,
                    "description": description,
                    "sort_order": sort_order,
                },
            )
            self._report("PricingPackageType", f"{name} ({hours}h)", created)

    def _report(self, model, label, created):
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created {model}: {label}"))
        else:
            self.stdout.write(self.style.WARNING(f"Skipped (already exists): {model} {label}"))
