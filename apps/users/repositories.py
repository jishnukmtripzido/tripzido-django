from .models import User


class UserRepository:
    @staticmethod
    def get_user_by_phone(phone_number: str):
        try:
            return User.objects.get(phone_number=phone_number)
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
        Persists a new User row.  Password is set to unusable because
        this platform authenticates exclusively via OTP.

        The phone_country_code is parsed from the phone_number prefix so
        it is stored separately for formatting convenience (matches the
        model's phone_country_code field).
        """
        # Derive country code from the number — e.g. "+91" from "+919876543210"
        # Simple heuristic: take everything up to the first digit run > 5 chars.
        # Adjust if you need stricter parsing (e.g. use the `phonenumbers` library).
        phone_country_code = ""
        if phone_number.startswith("+"):
            # Take the + and up to 3 following digits as the country code
            digits_only = phone_number[1:]
            for length in (3, 2, 1):
                phone_country_code = "+" + digits_only[:length]
                break  # simplest heuristic — replace with phonenumbers lib if needed

        user = User(
            phone_number=phone_number,
            phone_country_code=phone_country_code,
            first_name=first_name,
            last_name=last_name,
            email=email or None,
        )
        user.set_unusable_password()
        user.save()
        return user
