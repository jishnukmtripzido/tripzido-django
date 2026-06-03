




from .models import User


class UserRepository:
    @staticmethod
    def get_user_by_phone(phone_number: str):
        try:
            return User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return None