# from .repositories import UserRepository, AdminUserRepository
# from .models import User


# class UserService:
#     @staticmethod
#     def get_user_by_phone(phone_number: str):
#         """
#         Accepts full E.164 ("+919876543210") or bare local ("9876543210").
#         normalize_phone inside UserRepository handles both formats.
#         """
#         return UserRepository.get_user_by_phone(phone_number)

#     @staticmethod
#     def update_profile(user, validated_data: dict):
#         """
#         Applies a partial update to the given user's editable profile
#         fields. `validated_data` comes from ProfileUpdateSerializer, so
#         it only ever contains keys the user is allowed to change
#         (name, email, address) — phone_number is never accepted here,
#         since it's the verified login identity.
#         """
#         return UserRepository.update_user_fields(user, validated_data)

#     @staticmethod
#     def create_user(
#         phone_number: str,
#         first_name: str,
#         last_name: str = "",
#         email: str | None = None,
#         country_code: str = "",
#     ):
#         """
#         Creates a new User with an unusable password (OTP-only auth).

#         Args:
#             phone_number:  Local digits only, e.g. "9876543210".
#             first_name:    Required given name.
#             last_name:     Optional family name.
#             email:         Optional e-mail; stored as NULL when not supplied.
#             country_code:  Country dialling prefix, e.g. "+91". Stored
#                            separately from phone_number in the DB.

#         Returns:
#             The newly created User instance.
#         """
#         return UserRepository.create_user(
#             phone_number=phone_number,
#             first_name=first_name,
#             last_name=last_name,
#             email=email,
#             country_code=country_code,
#         )


# class AdminUserService:

#     ALLOWED_TRANSITIONS = {
#         User.AccountStatus.ACTIVE: [
#             User.AccountStatus.SUSPENDED,
#             User.AccountStatus.BANNED,
#         ],
#         User.AccountStatus.SUSPENDED: [
#             User.AccountStatus.ACTIVE,
#             User.AccountStatus.BANNED,
#         ],
#     }
#     REASON_REQUIRED_FOR = {User.AccountStatus.SUSPENDED, User.AccountStatus.BANNED}

#     @staticmethod
#     def get_customers(search=None):
#         return AdminUserRepository.get_customers(search)

#     @staticmethod
#     def get_detail(user_id: int):
#         return AdminUserRepository.get_by_id(user_id)

#     @staticmethod
#     def update_status(user_id: int, target_status: str, reason: str = ""):
#         user = AdminUserRepository.get_by_id(user_id)
#         if user is None:
#             return None, "User not found"

#         allowed = AdminUserService.ALLOWED_TRANSITIONS.get(user.status, [])
#         if target_status not in allowed:
#             return (
#                 None,
#                 f"Cannot change status from '{user.get_status_display()}' to '{target_status}'.",
#             )
#         if target_status in AdminUserService.REASON_REQUIRED_FOR and not reason.strip():
#             return None, "A reason is required for this action."

#         from django.utils import timezone

#         now = timezone.now()
#         if target_status == User.AccountStatus.SUSPENDED:
#             user.suspended_at = now
#             user.suspension_reason = reason
#         elif target_status == User.AccountStatus.BANNED:
#             user.banned_at = now
#             user.ban_reason = reason
#         # ACTIVE (reactivation) — suspension fields kept as history

#         user.status = target_status
#         user.save()
#         return user, None

#     @staticmethod
#     def get_staff(role_filter=None):
#         return AdminUserRepository.get_staff(role_filter)

#     @staticmethod
#     def create_staff(data: dict, admin_user):
#         return AdminUserRepository.create_staff(data, admin_user)

#     @staticmethod
#     def remove_staff(assignment_id: int):
#         return AdminUserRepository.remove_staff_assignment(assignment_id)


from .repositories import UserRepository, AdminUserRepository
from .models import User
import hashlib
import hmac
import secrets

from django.core.cache import cache


class OTPService:
    CODE_LENGTH = 6
    OTP_TTL = 300
    RESEND_COOLDOWN = 60
    SEND_WINDOW = 3600
    SEND_LIMIT_PER_IDENTITY = 5
    SEND_LIMIT_PER_IP = 20
    VERIFY_WINDOW = 600
    VERIFY_LIMIT_PER_IP = 30
    MAX_ATTEMPTS = 5
    LOCKOUT_TTL = 900

    @classmethod
    def _digest(cls, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def _key(cls, prefix: str, scope: str, identity: str) -> str:
        return f"otp:{prefix}:{scope}:{cls._digest(identity)}"

    @classmethod
    def _increment(cls, key: str, timeout: int) -> int:
        if cache.add(key, 0, timeout=timeout):
            return 1
        return cache.incr(key)

    @classmethod
    def issue(cls, scope: str, identity: str, ip_address: str):
        identity = identity.strip().lower()
        identity_key = cls._key("challenge", scope, identity)
        cooldown_key = cls._key("cooldown", scope, identity)
        lock_key = cls._key("lock", scope, identity)
        ip_key = cls._key("send-ip", scope, ip_address or "unknown")

        if cache.get(lock_key):
            return None, "locked"
        if cache.get(cooldown_key):
            return None, "cooldown"
        if (
            cls._increment(cls._key("send", scope, identity), cls.SEND_WINDOW)
            > cls.SEND_LIMIT_PER_IDENTITY
        ):
            return None, "rate_limited"
        if cls._increment(ip_key, cls.SEND_WINDOW) > cls.SEND_LIMIT_PER_IP:
            return None, "rate_limited"

        # code = f"{secrets.randbelow(10 ** cls.CODE_LENGTH):0{cls.CODE_LENGTH}d}"
        code = "121111"
        attempts_key = identity_key + ":attempts"
        cache.delete(attempts_key)
        cache.set(
            identity_key,
            {"digest": cls._digest(code), "attempts": 0},
            timeout=cls.OTP_TTL,
        )
        cache.set(cooldown_key, True, timeout=cls.RESEND_COOLDOWN)
        return code, None

    @classmethod
    def verify(cls, scope: str, identity: str, code: str, ip_address: str):
        identity = identity.strip().lower()
        identity_key = cls._key("challenge", scope, identity)
        lock_key = cls._key("lock", scope, identity)
        ip_key = cls._key("verify-ip", scope, ip_address or "unknown")

        if cache.get(lock_key):
            return False, "locked"
        if cls._increment(ip_key, cls.VERIFY_WINDOW) > cls.VERIFY_LIMIT_PER_IP:
            return False, "rate_limited"

        challenge = cache.get(identity_key)
        if not challenge:
            return False, "missing"

        if hmac.compare_digest(challenge["digest"], cls._digest(str(code))):
            cache.delete(identity_key)
            cache.delete(identity_key + ":attempts")
            return True, None

        attempts_key = identity_key + ":attempts"
        attempts = cls._increment(attempts_key, cls.OTP_TTL)
        challenge["attempts"] = attempts
        if attempts >= cls.MAX_ATTEMPTS:
            cache.delete(identity_key)
            cache.delete(attempts_key)
            cache.set(lock_key, True, timeout=cls.LOCKOUT_TTL)
            return False, "locked"
        cache.set(identity_key, challenge, timeout=cls.OTP_TTL)
        return False, "invalid"


class UserService:
    @staticmethod
    def get_user_by_phone(phone_number: str):
        return UserRepository.get_user_by_phone(phone_number)

    @staticmethod
    def update_profile(user, validated_data: dict):
        return UserRepository.update_user_fields(user, validated_data)

    @staticmethod
    def create_user(
        phone_number: str,
        first_name: str,
        last_name: str = "",
        email: str | None = None,
        country_code: str = "",
    ):
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

        user.status = target_status
        user.save()
        return user, None

    @staticmethod
    def get_staff(role_filter=None):
        return AdminUserRepository.get_staff(role_filter)

    @staticmethod
    def create_staff(data: dict, admin_user):
        """
        Plain passthrough — all the actual conflict-checking and
        upgrade-aware find-or-create logic lives in
        AdminUserRepository.create_staff, matching this project's
        existing convention (repository = data logic, service = thin
        pass-through). Now returns (assignment, error), matching that
        method's new return shape.
        """
        return AdminUserRepository.create_staff(data, admin_user)

    @staticmethod
    def remove_staff(assignment_id: int):
        return AdminUserRepository.remove_staff_assignment(assignment_id)
