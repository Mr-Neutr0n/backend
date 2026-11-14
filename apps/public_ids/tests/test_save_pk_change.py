"""Pointing a record at another row's pk never changes that row's code."""

import pytest

from apps.public_ids.models import PublicCodeModel

pytestmark = pytest.mark.django_db


def test_a_deleted_record_moved_onto_another_row_keeps_that_rows_code(
    thing_model: type[PublicCodeModel],
) -> None:
    first = thing_model._default_manager.create(label="made-up one")
    second = thing_model._default_manager.create(label="made-up two")
    first.delete()
    first.pk = second.pk

    with pytest.raises(ValueError, match="never changes"):
        first.save()

    stored = thing_model._default_manager.get(pk=second.pk)
    assert stored.public_code == second.public_code


def test_a_loaded_record_moved_onto_another_row_keeps_that_rows_code(
    thing_model: type[PublicCodeModel],
) -> None:
    first = thing_model._default_manager.create(label="made-up one")
    second = thing_model._default_manager.create(label="made-up two")
    loaded = thing_model._default_manager.get(pk=first.pk)
    loaded.pk = second.pk

    with pytest.raises(ValueError, match="never changes"):
        loaded.save()

    stored = thing_model._default_manager.get(pk=second.pk)
    assert stored.public_code == second.public_code
