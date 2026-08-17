from django.core.management.base import BaseCommand
from apps.users.models import User, Role, UserRoleAssignment


class Command(BaseCommand):
    help = "Creates or updates a staff account with SUPPORT or SUPER_ADMIN admin-portal access."

    def add_arguments(self, parser):
        parser.add_argument("email", type=str)
        parser.add_argument("password", type=str)
        parser.add_argument(
            "--role", type=str, default="SUPPORT", choices=["SUPPORT", "SUPER_ADMIN"]
        )
        parser.add_argument("--first-name", type=str, default="Staff")
        parser.add_argument("--last-name", type=str, default="")
        # 1. Add the new argument here:
        parser.add_argument("--phone", type=str, default="+00000000000")

    def handle(self, *args, **options):
        email = options["email"]

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": options["first_name"],
                "last_name": options["last_name"],
                "phone_number": options["phone"],  # 2. Use it here
            },
        )
        user.set_password(options["password"])
        user.save()

        role, _ = Role.objects.get_or_create(
            system_role=options["role"],
            defaults={"is_system": True},
        )
        UserRoleAssignment.objects.get_or_create(user=user, role=role)

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Updated'} staff user {email} with role {options['role']}."
            )
        )
