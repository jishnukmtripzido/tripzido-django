from .models import User, Role, UserRoleAssignment
from django.db.models import Q
import phonenumbers


def normalize_phone(phone_number: str) -> tuple[str, str]:
    """
    Accepts any phone number format and returns (local_number, country_code).

    Examples:
        "+919876543210" -> ("9876543210", "+91")
        "9876543210"    -> ("9876543210", "")   # no country code to parse
        "+14155552671"  -> ("4155552671", "+1")

    Always use this helper everywhere a phone number is touched so the
    format stored in DB and used for cache keys is always consistent.
    """
    phone_number = phone_number.strip()
    try:
        parsed = phonenumbers.parse(phone_number)
        local_number = str(parsed.national_number)
        country_code = f"+{parsed.country_code}"
        return local_number, country_code
    except phonenumbers.NumberParseException:
        # Already a bare local number with no country prefix — return as-is
        return phone_number, ""


class UserRepository:

    @staticmethod
    def get_user_by_phone(phone_number: str):
        """
        Accepts full E.164 ("+919876543210") or bare local ("9876543210").
        Always strips the country code before querying, since phone_number
        is stored as the local number only.
        """
        local_number, _ = normalize_phone(phone_number)
        try:
            return User.objects.get(phone_number=local_number)
        except User.DoesNotExist:
            return None

    @staticmethod
    def update_user_fields(user: User, fields: dict) -> User:
        """
        Updates only the given fields on the user instance and saves.
        `fields` is expected to already be validated (e.g. via
        ProfileUpdateSerializer.validated_data) — this method does no
        validation of its own, it just assigns and persists.
        """
        for field_name, value in fields.items():
            setattr(user, field_name, value)
        user.save(update_fields=list(fields.keys()))
        return user

    @staticmethod
    def create_user(
        phone_number: str,
        first_name: str,
        last_name: str = "",
        email: str | None = None,
        country_code: str | None = None,
    ):
        """
        Persists a new User row.

        phone_number can be E.164 ("+919876543210") or bare local ("9876543210").
        If country_code is supplied by the caller (e.g. already parsed during
        send-otp and cached), it's used as-is — this avoids re-deriving it from
        a bare local number, which has no prefix left to parse.
        Password is set to unusable — OTP-only auth platform.
        """
        local_number, derived_country_code = normalize_phone(phone_number)

        user = User(
            phone_number=local_number,  # "9876543210"
            phone_country_code=country_code or derived_country_code,  # "+91"
            first_name=first_name,
            last_name=last_name,
            email=email or None,
        )
        user.set_unusable_password()
        user.save()
        return user


class AdminUserRepository:

    STAFF_ROLES = [Role.SystemRole.SUPPORT, Role.SystemRole.SUPER_ADMIN]

    @staticmethod
    def get_customers(search=None):
        # "Customer" = anyone NOT currently holding VENDOR/SUPPORT/
        # SUPER_ADMIN. Broader than requiring a CUSTOMER
        # UserRoleAssignment to exist, since it's unconfirmed that
        # signup always creates one — this definition can't
        # accidentally exclude a real customer.
        qs = (
            User.objects.exclude(
                role_assignments__role__system_role__in=[
                    Role.SystemRole.VENDOR,
                    Role.SystemRole.SUPPORT,
                    Role.SystemRole.SUPER_ADMIN,
                ]
            )
            .distinct()
            .order_by("-created_at")
        )
        if search:
            qs = qs.filter(
                Q(phone_number__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )
        return qs

    @staticmethod
    def get_by_id(user_id: int):
        return User.objects.filter(id=user_id).first()

    @staticmethod
    def get_staff(role_filter=None):
        qs = (
            UserRoleAssignment.objects.filter(
                role__system_role__in=AdminUserRepository.STAFF_ROLES
            )
            .select_related("user", "role", "assigned_by")
            .order_by("-created_at")
        )
        if role_filter:
            qs = qs.filter(role__system_role=role_filter)
        return qs

    @staticmethod
    def create_staff(data: dict, admin_user):
        user, _ = User.objects.get_or_create(
            phone_number=data["phone_number"],
            defaults={
                "phone_country_code": data.get("phone_country_code", "+91"),
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "email": data["email"],
            },
        )
        # If the user already existed (e.g. promoting an existing
        # customer to staff), keep their phone/history but make sure
        # email + password are actually set so they can log into the
        # admin portal.
        user.email = data["email"]
        user.set_password(data["password"])
        if data.get("first_name"):
            user.first_name = data["first_name"]
        if data.get("last_name"):
            user.last_name = data["last_name"]
        user.save()

        role, _ = Role.objects.get_or_create(
            system_role=data["role"],
            defaults={"is_system": True},
        )
        assignment, _ = UserRoleAssignment.objects.get_or_create(
            user=user,
            role=role,
            defaults={"assigned_by": admin_user},
        )
        return assignment

    @staticmethod
    def remove_staff_assignment(assignment_id: int):
        assignment = (
            UserRoleAssignment.objects.filter(id=assignment_id)
            .select_related("role")
            .first()
        )
        if assignment is None:
            return False, "not_found"
        if assignment.role.system_role == Role.SystemRole.SUPER_ADMIN:
            remaining = (
                UserRoleAssignment.objects.filter(
                    role__system_role=Role.SystemRole.SUPER_ADMIN
                )
                .exclude(id=assignment_id)
                .count()
            )
            if remaining == 0:
                return False, "last_super_admin"
        assignment.delete()
        return True, None
