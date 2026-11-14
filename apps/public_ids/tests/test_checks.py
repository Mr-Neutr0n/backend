"""The system check reports a concrete public-code model without a type."""

from django.apps.registry import Apps
from django.core import checks
from django.db import models
from django.test.utils import isolate_apps

from apps.public_ids.checks import check_public_code_types
from apps.public_ids.codes import CodeType
from apps.public_ids.models import PublicCodeModel


def _errors(isolated: Apps | None) -> list[checks.CheckMessage]:
    assert isolated is not None
    return check_public_code_types(app_configs=[isolated.get_app_config("public_ids")])


def test_concrete_model_without_a_type_is_reported() -> None:
    with isolate_apps("apps.public_ids") as isolated:

        class Untyped(PublicCodeModel):
            class Meta:
                app_label = "public_ids"

        errors = _errors(isolated)

    assert [error.id for error in errors] == ["public_ids.E001"]
    assert errors[0].obj is Untyped
    assert errors[0].level == checks.ERROR


def test_concrete_model_with_a_type_passes() -> None:
    with isolate_apps("apps.public_ids") as isolated:

        class Typed(PublicCodeModel):
            public_code_type = CodeType.CLUB

            class Meta:
                app_label = "public_ids"

        assert _errors(isolated) == []


def test_abstract_model_without_a_type_is_ignored() -> None:
    with isolate_apps("apps.public_ids") as isolated:

        class Base(PublicCodeModel):
            class Meta:
                abstract = True
                app_label = "public_ids"

        class Other(models.Model):  # noqa: DJ008
            class Meta:
                app_label = "public_ids"

        assert _errors(isolated) == []


def test_a_subclass_inherits_its_parents_type() -> None:
    with isolate_apps("apps.public_ids") as isolated:

        class Base(PublicCodeModel):
            public_code_type = CodeType.EVENT

            class Meta:
                abstract = True
                app_label = "public_ids"

        class Child(Base):
            class Meta:
                app_label = "public_ids"

        assert _errors(isolated) == []


def test_check_is_registered() -> None:
    registered: list[object] = list(checks.registry.registry.get_checks())

    assert check_public_code_types in registered


def test_installed_models_pass() -> None:
    assert check_public_code_types(app_configs=None) == []
