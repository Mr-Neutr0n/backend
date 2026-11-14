"""A failed child create leaves every primary key as it was before."""

import pytest
from django.db import IntegrityError

from apps.public_ids.models import PublicCodeModel

pytestmark = pytest.mark.django_db

Models = tuple[type[PublicCodeModel], type[PublicCodeModel]]


def test_a_failed_child_create_resets_parent_keys(parent_and_child: Models) -> None:
    _, kid_model = parent_and_child
    kid_model._default_manager.create(label="made-up one", nickname="same")
    kid = kid_model(label="made-up two", nickname="same")

    # The parent row inserts, then the child row fails on its nickname.
    with pytest.raises(IntegrityError):
        kid.save()

    assert kid.pk is None
    assert kid.id is None  # type: ignore[attr-defined]
    assert kid.public_code is None
    assert kid._state.adding is True

    kid.nickname = "different"
    kid.save()

    assert kid_model._default_manager.filter(pk=kid.pk).exists()
