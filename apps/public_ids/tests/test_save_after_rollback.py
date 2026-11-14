"""Saving a record whose create rolled back raises instead of inserting."""

import pytest
from django.db import DatabaseError, transaction

from apps.public_ids.models import IssuedCode, PublicCodeModel

pytestmark = pytest.mark.django_db


class _RollBack(Exception):
    pass


def _create_then_roll_back(thing: PublicCodeModel) -> None:
    with transaction.atomic():
        thing.save()
        raise _RollBack


def test_saving_after_a_rolled_back_create_never_inserts(
    thing_model: type[PublicCodeModel],
) -> None:
    thing = thing_model(label="made-up one")
    with pytest.raises(_RollBack):
        _create_then_roll_back(thing)
    assert not IssuedCode.objects.filter(code=thing.public_code).exists()

    with pytest.raises(DatabaseError), transaction.atomic():
        thing.save()

    assert thing_model._default_manager.count() == 0
    assert IssuedCode.objects.count() == 0
