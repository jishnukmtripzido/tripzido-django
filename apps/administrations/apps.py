from django.apps import AppConfig


class AdministrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.administrations"

    def ready(self):
        import apps.administrations.signals  # noqa: F401
