from django.apps import AppConfig
from django.core import checks


class PublicIdsConfig(AppConfig):
    name = "apps.public_ids"
    verbose_name = "Public identifiers"

    def ready(self) -> None:
        from apps.public_ids.checks import check_public_code_types

        checks.register(check_public_code_types, checks.Tags.models)
