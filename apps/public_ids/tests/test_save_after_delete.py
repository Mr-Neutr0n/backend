"""Saving a deleted record raises instead of inserting it again."""

import pytest

from apps.public_ids.models import PublicCodeModel

pytestmark = pytest.mark.django_db


def test_saving_a_deleted_record_never_inserts(
    thing_model: type[PublicCodeModel],
) -> None:
    thing = thing_model._default_manager.create(label="made-up one")
    code = thing.public_code
    thing.delete()

    with pytest.raises(ValueError, match="primary key"):
        thing.save()

    assert thing_model._default_manager.count() == 0
    assert not thing_model._default_manager.filter(public_code=code).exists()
