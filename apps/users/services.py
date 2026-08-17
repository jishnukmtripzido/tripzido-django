from .repositories import UserRepository, AdminUserRepository
from .models import User


class UserService:
    @staticmethod
    def get_user_by_phone(phone_number: str):
        """
        Accepts full E.164 ("+919876543210") or bare local ("9876543210").
        normalize_phone inside UserRepository handles both formats.
        """
        return UserRepository.get_user_by_phone(phone_number)

    @staticmethod
    def update_profile(user, validated_data: dict):
        """
        Applies a partial update to the given user's editable profile
        fields. `validated_data` comes from ProfileUpdateSerializer, so
        it only ever contains keys the user is allowed to change
        (name, email, address) — phone_number is never accepted here,
        since it's the verified login identity.
        """
        return UserRepository.update_user_fields(user, validated_data)

    @staticmethod
    def create_user(
        phone_number: str,
        first_name: str,
        last_name: str = "",
        email: str | None = None,
        country_code: str = "",
    ):
        """
        Creates a new User with an unusable password (OTP-only auth).

        Args:
            phone_number:  Local digits only, e.g. "9876543210".
            first_name:    Required given name.
            last_name:     Optional family name.
            email:         Optional e-mail; stored as NULL when not supplied.
            country_code:  Country dialling prefix, e.g. "+91". Stored
                           separately from phone_number in the DB.

        Returns:
            The newly created User instance.
        """
        return UserRepository.create_user(
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            country_code=country_code,
        )


class AdminUserService:

    ALLOWED_TRANSITIONS = {
        User.AccountStatus.ACTIVE: [
            User.AccountStatus.SUSPENDED,
            User.AccountStatus.BANNED,
        ],
        User.AccountStatus.SUSPENDED: [
            User.AccountStatus.ACTIVE,
            User.AccountStatus.BANNED,
        ],
    }
    REASON_REQUIRED_FOR = {User.AccountStatus.SUSPENDED, User.AccountStatus.BANNED}

    @staticmethod
    def get_customers(search=None):
        return AdminUserRepository.get_customers(search)

    @staticmethod
    def get_detail(user_id: int):
        return AdminUserRepository.get_by_id(user_id)

    @staticmethod
    def update_status(user_id: int, target_status: str, reason: str = ""):
        user = AdminUserRepository.get_by_id(user_id)
        if user is None:
            return None, "User not found"

        allowed = AdminUserService.ALLOWED_TRANSITIONS.get(user.status, [])
        if target_status not in allowed:
            return (
                None,
                f"Cannot change status from '{user.get_status_display()}' to '{target_status}'.",
            )
        if target_status in AdminUserService.REASON_REQUIRED_FOR and not reason.strip():
            return None, "A reason is required for this action."

        from django.utils import timezone

        now = timezone.now()
        if target_status == User.AccountStatus.SUSPENDED:
            user.suspended_at = now
            user.suspension_reason = reason
        elif target_status == User.AccountStatus.BANNED:
            user.banned_at = now
            user.ban_reason = reason
        # ACTIVE (reactivation) — suspension fields kept as history

        user.status = target_status
        user.save()
        return user, None

    @staticmethod
    def get_staff(role_filter=None):
        return AdminUserRepository.get_staff(role_filter)

    @staticmethod
    def create_staff(data: dict, admin_user):
        return AdminUserRepository.create_staff(data, admin_user)

    @staticmethod
    def remove_staff(assignment_id: int):
        return AdminUserRepository.remove_staff_assignment(assignment_id)
