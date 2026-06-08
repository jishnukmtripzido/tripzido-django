# apps/locations/repositories.py

from apps.locations.models import Country, State, City, PickupLocation


class CountryRepository:

    @staticmethod
    def get_all():
        return Country.objects.all()

    @staticmethod
    def get_by_id(country_id: int):
        return Country.objects.filter(id=country_id).first()

    @staticmethod
    def create(data: dict):
        return Country.objects.create(**data)

    @staticmethod
    def update(instance: Country, data: dict):
        for key, value in data.items():
            setattr(instance, key, value)
        instance.save()
        return instance

    @staticmethod
    def delete(instance: Country):
        instance.delete()


class StateRepository:

    @staticmethod
    def get_all():
        return State.objects.select_related("country").all()

    @staticmethod
    def get_by_id(state_id: int):
        return State.objects.select_related("country").filter(id=state_id).first()

    @staticmethod
    def create(data: dict):
        return State.objects.create(**data)

    @staticmethod
    def update(instance: State, data: dict):
        for key, value in data.items():
            setattr(instance, key, value)
        instance.save()
        return instance

    @staticmethod
    def delete(instance: State):
        instance.delete()


class CityRepository:

    @staticmethod
    def get_all(filters: dict = None):
        queryset = City.objects.select_related("state").all()
        return queryset  # return queryset, not list — views/filters need it

    @staticmethod
    def get_by_id(city_id: int):
        return City.objects.select_related("state").filter(id=city_id).first()

    @staticmethod
    def create(data: dict):
        return City.objects.create(**data)

    @staticmethod
    def update(instance: City, data: dict):
        for key, value in data.items():
            setattr(instance, key, value)
        instance.save()
        return instance

    @staticmethod
    def delete(instance: City):
        instance.delete()


class PickupLocationRepository:

    @staticmethod
    def get_all():
        return PickupLocation.objects.select_related("city").all()

    @staticmethod
    def get_by_id(location_id: int):
        return (
            PickupLocation.objects.select_related("city").filter(id=location_id).first()
        )

    @staticmethod
    def create(data: dict):
        return PickupLocation.objects.create(**data)

    @staticmethod
    def update(instance: PickupLocation, data: dict):
        for key, value in data.items():
            setattr(instance, key, value)
        instance.save()
        return instance

    @staticmethod
    def delete(instance: PickupLocation):
        instance.delete()
