from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.administrations.models import TaxRate


class Command(BaseCommand):
    """
    Seeds the current tax rate for each TaxRate context:

      VENDOR_RENTAL        — tax on the rental the vendor sells the customer
      PLATFORM_COMMISSION  — tax on the platform's commission to the vendor

    With no current rate, bookings record 0% tax and an empty tax snapshot.

    Rates are a legal/accounting decision, so nothing is assumed: both
    percentages must be passed explicitly (confirm them and the SAC codes
    with your CA). That's also why seed_initial_data doesn't run this.

      python manage.py seed_tax_rates --rental 18 --commission 18 \\
          --rental-sac 9966 --commission-sac 9985

    --split cgst-sgst (default) records half as CGST and half as SGST
    (intra-state); --split igst records it all as IGST (inter-state).

    Idempotent — a context that already has a current rate is skipped,
    so this never publishes a new version over the admin's.
    """

    help = "Seeds current VENDOR_RENTAL and PLATFORM_COMMISSION tax rates (values required)."

    def add_arguments(self, parser):
        parser.add_argument("--rental", required=True, help="VENDOR_RENTAL tax %%, e.g. 18")
        parser.add_argument("--commission", required=True, help="PLATFORM_COMMISSION tax %%, e.g. 18")
        parser.add_argument("--rental-sac", default="", help="SAC code for rental, from your CA.")
        parser.add_argument("--commission-sac", default="", help="SAC code for commission, from your CA.")
        parser.add_argument(
            "--split",
            choices=["cgst-sgst", "igst"],
            default="cgst-sgst",
            help="How the rate is shown on invoices (default: cgst-sgst).",
        )

    def handle(self, *args, **options):
        rates = [
            (TaxRate.Context.VENDOR_RENTAL, options["rental"], options["rental_sac"]),
            (TaxRate.Context.PLATFORM_COMMISSION, options["commission"], options["commission_sac"]),
        ]
        for context, raw_percentage, sac in rates:
            label = TaxRate.Context(context).label
            percentage = self._parse_percentage(label, raw_percentage)

            current = TaxRate.objects.filter(context=context, is_current=True).first()
            if current:
                self.stdout.write(
                    self.style.WARNING(f"Skipped: {label} already has a current rate ({current}).")
                )
                continue

            if options["split"] == "igst":
                cgst = sgst = Decimal("0")
                igst = percentage
            else:
                cgst = sgst = (percentage / 2).quantize(Decimal("0.01"))
                igst = Decimal("0")

            rate = TaxRate.objects.create(
                context=context,
                name=f"GST {percentage.normalize():f}%",
                percentage=percentage,
                cgst_percentage=cgst,
                sgst_percentage=sgst,
                igst_percentage=igst,
                hsn_sac_code=sac,
                is_current=True,
                effective_from=timezone.localdate(),
            )
            self.stdout.write(self.style.SUCCESS(f"Created {label}: {rate}"))

    @staticmethod
    def _parse_percentage(label, raw) -> Decimal:
        try:
            value = Decimal(str(raw)).quantize(Decimal("0.01"))
        except InvalidOperation:
            raise CommandError(f"{label}: '{raw}' is not a number.")
        if not Decimal("0") <= value <= Decimal("100"):
            raise CommandError(f"{label}: percentage must be between 0 and 100.")
        return value
