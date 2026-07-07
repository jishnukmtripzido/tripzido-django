from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Orchestrator — runs every app-level seed command in the right order.
    Each individual seed command (seed_platform_config, etc.) stays
    independently runnable and owned by its own app; this just wires
    them together for a one-shot fresh environment setup.
    """

    help = "Runs all app-level seed commands in dependency order. Idempotent — safe to re-run."

    # Order matters if a later seed depends on an earlier one existing
    # (e.g. a CancellationPolicy seed might reference a default admin
    # user, or PlatformConfig keys other seeders read at import time).
    SEED_COMMANDS = [
        "seed_platform_config",
        "seed_cancellation_policy",  # add as you build more seeders
        # "seed_default_subscription_plan",
        # "seed_legal_documents",
    ]

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding initial data...\n"))

        for command_name in self.SEED_COMMANDS:
            self.stdout.write(self.style.MIGRATE_LABEL(f"→ {command_name}"))
            try:
                call_command(command_name)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Failed: {command_name} — {e}"))
                raise
            self.stdout.write("")

        self.stdout.write(self.style.SUCCESS("All seed commands completed."))
