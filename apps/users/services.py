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
