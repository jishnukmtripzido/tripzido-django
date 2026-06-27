from .models import User
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
    ):
        """
        Persists a new User row.

        phone_number can be E.164 ("+919876543210") or bare local ("9876543210").
        The local number is stored in phone_number, country code separately.
        Password is set to unusable — OTP-only auth platform.
        """
        local_number, country_code = normalize_phone(phone_number)

        user = User(
            phone_number=local_number,  # "9876543210"
            phone_country_code=country_code,  # "+91"
            first_name=first_name,
            last_name=last_name,
            email=email or None,
        )
        user.set_unusable_password()
        user.save()
        return user
