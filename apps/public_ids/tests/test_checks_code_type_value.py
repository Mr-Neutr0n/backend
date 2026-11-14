"""The system check requires public_code_type to be a CodeType."""

from django.test.utils import isolate_apps

from apps.public_ids.checks import check_public_code_types
from apps.public_ids.models import PublicCodeModel


def test_a_code_type_that_is_not_a_code_type_is_reported() -> None:
    with isolate_apps("apps.public_ids") as isolated:

        class WrongType(PublicCodeModel):
            public_code_type = "P"  # type: ignore[assignment]

            class Meta:
                app_label = "public_ids"

        assert isolated is not None
        errors = check_public_code_types(
            app_configs=[isolated.get_app_config("public_ids")]
        )

    assert [error.id for error in errors] == ["public_ids.E001"]
    assert errors[0].obj is WrongType
