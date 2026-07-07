from django.core.management.base import BaseCommand
from apps.administrations.models import CancellationPolicy, CancellationTier


class Command(BaseCommand):
    """
    Seeds the default CancellationPolicy + its tiers, matching the
    CP-1 policy already configured in the admin panel:

      FULL   72–∞  hrs → 25%  refund
      FULL   24–72 hrs → 75%  refund
      FULL   0–24  hrs → 100% refund
      PARTIAL 0–∞  hrs → 0%   refund

    Idempotent — safe to re-run. If a policy with this name already
    exists, it's skipped entirely (including its tiers) rather than
    duplicated or overwritten, since CancellationPolicy.save() already
    handles "only one is_current per policy" — we don't want a re-run
    of this command to silently create a second CP-1 and flip
    is_current on it.
    """

    help = "Seeds the default cancellation policy and tiers if none exists yet."

    POLICY_NAME = "CP-1"
    REFUND_NOTE = "Refunds are processed within 5-12 business days."

    TIERS = [
        # (payment_mode, min_hours, max_hours, refund_pct, label, description)
        (
            CancellationTier.PaymentMode.FULL,
            72,
            None,
            "25.00",
            "If cancelled before 72 hours from pickup time",
            "25% Deduction",
        ),
        (
            CancellationTier.PaymentMode.FULL,
            24,
            72,
            "75.00",
            "If cancelled between 72 and 24 hours before pickup",
            "75% Deduction",
        ),
        (
            CancellationTier.PaymentMode.FULL,
            0,
            24,
            "100.00",
            "If cancelled within 24 hours of pickup time",
            "100% Deduction",
        ),
        (
            CancellationTier.PaymentMode.PARTIAL,
            0,
            None,
            "0.00",
            "Any time before pickup",
            "No refund - 100% Deduction",
        ),
    ]

    def handle(self, *args, **options):
        if CancellationPolicy.objects.filter(name=self.POLICY_NAME).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped: CancellationPolicy '{self.POLICY_NAME}' already exists."
                )
            )
            return

        policy = CancellationPolicy.objects.create(
            name=self.POLICY_NAME,
            is_current=True,
            refund_note=self.REFUND_NOTE,
        )

        for payment_mode, min_h, max_h, refund_pct, label, description in self.TIERS:
            CancellationTier.objects.create(
                policy=policy,
                payment_mode=payment_mode,
                min_hours_before_pickup=min_h,
                max_hours_before_pickup=max_h,
                refund_percentage=refund_pct,
                label=label,
                description=description,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created CancellationPolicy '{self.POLICY_NAME}' (v{policy.version}) "
                f"with {len(self.TIERS)} tiers."
            )
        )
