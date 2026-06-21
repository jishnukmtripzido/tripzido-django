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
