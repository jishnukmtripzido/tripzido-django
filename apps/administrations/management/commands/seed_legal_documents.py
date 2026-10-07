from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.administrations.models import LegalDocument


class Command(BaseCommand):
    """
    Seeds a current Platform T&C and Privacy Policy if none exists yet.

    Checkout records which T&C version each customer accepted
    (CustomerTCAcceptance); with no current PLATFORM_TC, bookings still go
    through but no acceptance is recorded at all.

    Pass the real text with --tc-file / --privacy-file (HTML or Markdown,
    whatever the admin editor stores). Without a file, a clearly marked
    PLACEHOLDER is created so a fresh environment works — replace it from
    the admin portal before going live; customers would otherwise accept
    the placeholder.

    Idempotent — a doc type that already has a current version is skipped,
    so this never publishes a new version over the admin's.
    """

    help = "Seeds current Platform T&C and Privacy Policy documents if missing."

    PLACEHOLDER = (
        "<p><strong>PLACEHOLDER — {title} not yet published.</strong></p>"
        "<p>Replace this document from the admin portal before going live.</p>"
    )

    def add_arguments(self, parser):
        parser.add_argument("--tc-file", help="File with the Platform T&C content.")
        parser.add_argument("--privacy-file", help="File with the Privacy Policy content.")

    def handle(self, *args, **options):
        docs = [
            (LegalDocument.DocType.PLATFORM_TC, options.get("tc_file")),
            (LegalDocument.DocType.PRIVACY_POLICY, options.get("privacy_file")),
        ]
        for doc_type, file_path in docs:
            title = LegalDocument.DocType(doc_type).label

            current = LegalDocument.objects.filter(doc_type=doc_type, is_current=True).first()
            if current:
                self.stdout.write(
                    self.style.WARNING(f"Skipped: {title} v{current.version} is already current.")
                )
                continue

            if file_path:
                path = Path(file_path)
                if not path.is_file():
                    raise CommandError(f"{title}: file not found: {file_path}")
                content = path.read_text(encoding="utf-8").strip()
                if not content:
                    raise CommandError(f"{title}: file is empty: {file_path}")
            else:
                content = self.PLACEHOLDER.format(title=title)

            # version is assigned by LegalDocument.save().
            doc = LegalDocument.objects.create(
                doc_type=doc_type,
                content=content,
                is_current=True,
                published_at=timezone.now(),
            )

            if file_path:
                self.stdout.write(self.style.SUCCESS(f"Created {title} v{doc.version} from {file_path}."))
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Created PLACEHOLDER {title} v{doc.version} - replace it from "
                        "the admin portal before going live."
                    )
                )
