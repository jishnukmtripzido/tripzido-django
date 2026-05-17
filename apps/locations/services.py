# apps/locations/services.py

from django.core.exceptions import ValidationError
from apps.locations.repositories import (
    CountryRepository, StateRepository,
    CityRepository, PickupLocationRepository
)


class CountryService:

    @staticmethod
    def get_all():
        return CountryRepository.get_all()

    @staticmethod
    def get_by_id(country_id: int):
        country = CountryRepository.get_by_id(country_id)
        if not country:
            raise ValidationError(f"Country {country_id} not found.")
        return country

    @staticmethod
    def create(data: dict):
        return CountryRepository.create(data)

    @staticmethod
    def update(country_id: int, data: dict):
        country = CountryService.get_by_id(country_id)
        return CountryRepository.update(country, data)

    @staticmethod
    def delete(country_id: int):
        country = CountryService.get_by_id(country_id)
        CountryRepository.delete(country)


class StateService:

    @staticmethod
    def get_all():
        return StateRepository.get_all()

    @staticmethod
    def get_by_id(state_id: int):
        state = StateRepository.get_by_id(state_id)
        if not state:
            raise ValidationError(f"State {state_id} not found.")
        return state

    @staticmethod
    def create(data: dict):
        # business rule — validate country exists
        country_id = data.get("country_id")
        if not country_id:
            raise ValidationError("Country is required.")
        return StateRepository.create(data)

    @staticmethod
    def update(state_id: int, data: dict):
        state = StateService.get_by_id(state_id)
        return StateRepository.update(state, data)

    @staticmethod
    def delete(state_id: int):
        state = StateService.get_by_id(state_id)
        StateRepository.delete(state)


class CityService:

    @staticmethod
    def get_all():
        return CityRepository.get_all()

    @staticmethod
    def get_by_id(city_id: int):
        city = CityRepository.get_by_id(city_id)
        if not city:
            raise ValidationError(f"City {city_id} not found.")
        return city

    @staticmethod
    def create(data: dict):
        return CityRepository.create(data)

    @staticmethod
    def update(city_id: int, data: dict):
        city = CityService.get_by_id(city_id)
        return CityRepository.update(city, data)

    @staticmethod
    def delete(city_id: int):
        city = CityService.get_by_id(city_id)
        CityRepository.delete(city)


class PickupLocationService:

    @staticmethod
    def get_all():
        return PickupLocationRepository.get_all()

    @staticmethod
    def get_by_id(location_id: int):
        location = PickupLocationRepository.get_by_id(location_id)
        if not location:
            raise ValidationError(f"PickupLocation {location_id} not found.")
        return location

    @staticmethod
    def create(data: dict):
        return PickupLocationRepository.create(data)

    @staticmethod
    def update(location_id: int, data: dict):
        location = PickupLocationService.get_by_id(location_id)
        return PickupLocationRepository.update(location, data)

    @staticmethod
    def delete(location_id: int):
        location = PickupLocationService.get_by_id(location_id)
        PickupLocationRepository.delete(location)