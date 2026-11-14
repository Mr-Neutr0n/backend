"""System checks for models with a public code."""

from collections.abc import Sequence
from typing import Any

from django.apps import AppConfig, apps
from django.core import checks

from apps.public_ids.codes import CodeType
from apps.public_ids.models import PublicCodeModel


def check_public_code_types(
    app_configs: Sequence[AppConfig] | None = None, **kwargs: Any
) -> list[checks.CheckMessage]:
    """Report every concrete PublicCodeModel without a CodeType as its type."""
    if app_configs is None:
        models = apps.get_models()
    else:
        models = [model for config in app_configs for model in config.get_models()]
    return [
        checks.Error(
            "A model with a public code must set public_code_type to a CodeType.",
            hint="Set public_code_type to a CodeType member.",
            obj=model,
            id="public_ids.E001",
        )
        for model in models
        if issubclass(model, PublicCodeModel)
        and not isinstance(getattr(model, "public_code_type", None), CodeType)
    ]
