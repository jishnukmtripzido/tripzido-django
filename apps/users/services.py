from .repositories import UserRepository


class UserService:
    @staticmethod
    def get_user_by_phone(phone_number: str):

        return UserRepository.get_user_by_phone(phone_number)
