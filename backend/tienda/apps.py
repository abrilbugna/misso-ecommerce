from django.apps import AppConfig


class TiendaConfig(AppConfig):
    name = 'tienda'

    def ready(self):
        from . import subscription_checks  # noqa: F401
