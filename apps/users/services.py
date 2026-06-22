from .repositories import UserRepository


class UserService:
    @staticmethod
    def get_user_by_phone(phone_number: str):

        return UserRepository.get_user_by_phone(phone_number)

    @staticmethod
    def update_profile(user, validated_data: dict):
        """
        Applies a partial update to the given user's editable profile
        fields. `validated_data` comes from ProfileUpdateSerializer, so
        it only ever contains keys the user is allowed to change
        (name, email, address) — phone_number is never accepted here,
        since it's the verified login identity (see BasicDetails.tsx,
        where Mobile Number has no Edit affordance).
        """
        return UserRepository.update_user_fields(user, validated_data)

    @staticmethod
    def create_user(
        phone_number: str,
        first_name: str,
        last_name: str = "",
        email: str | None = None,
    ):
        """
        Creates a new User with an unusable password (OTP-only auth).

        Args:
            phone_number: Primary identifier, e.g. "+919876543210".
            first_name:   Required given name.
            last_name:    Optional family name.
            email:        Optional e-mail; stored as NULL when not supplied.

        Returns:
            The newly created User instance.
        """
        return UserRepository.create_user(
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )
