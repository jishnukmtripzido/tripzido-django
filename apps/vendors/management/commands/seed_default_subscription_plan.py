from django.core.management.base import BaseCommand
from apps.vendors.models import SubscriptionPlan, VendorCommission


class Command(BaseCommand):
    """
    Seeds the default commission structure and subscription plan.

    A vendor's commission comes from their current subscription plan's
    VendorCommission; a vendor with no plan is charged 0% and can't offer
    partial payment. Plans are assigned to vendors by an admin (Admin
    portal → vendor → assign plan) — this only makes sure one exists.

    Idempotent — skipped entirely if a default plan already exists, so a
    re-run never creates a second default or overwrites admin edits.
    """

    help = "Seeds the default vendor commission and subscription plan if none is marked default."

    COMMISSION_NAME = "Standard 10%"
    COMMISSION_PERCENTAGE = "10.00"

    PLAN_NAME = "Free"

    def handle(self, *args, **options):
        # Messages use plan.name, not str(plan): __str__ includes "₹",
        # which Windows consoles (cp1252) can't encode.
        existing = SubscriptionPlan.objects.filter(is_default=True).first()
        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped: default SubscriptionPlan already exists ({existing.name})."
                )
            )
            return

        commission, created = VendorCommission.objects.get_or_create(
            name=self.COMMISSION_NAME,
            defaults={
                "commission_type": VendorCommission.CommissionType.FLAT,
                "flat_percentage": self.COMMISSION_PERCENTAGE,
                "description": "Flat platform commission on every booking.",
            },
        )
        self.stdout.write(
            self.style.SUCCESS(f"Created VendorCommission: {commission}")
            if created
            else self.style.WARNING(f"Reusing existing VendorCommission: {commission}")
        )

        plan = SubscriptionPlan.objects.create(
            name=self.PLAN_NAME,
            description="Default plan for new vendors.",
            billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
            price="0.00",
            commission=commission,
            max_listings=None,  # unlimited
            max_pickup_locations=None,  # unlimited
            max_images_per_listing=4,
            can_enable_partial_payment=True,
            can_access_analytics=False,
            can_respond_to_reviews=True,
            priority_listing=False,
            is_default=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Created default SubscriptionPlan: {plan.name} "
                f"({plan.billing_cycle}, Rs {plan.price}, {commission.flat_percentage}% commission)"
            )
        )
