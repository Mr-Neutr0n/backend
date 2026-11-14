"""A new child instance never overwrites its parent row's code."""

import pytest
from django.db import IntegrityError, transaction

from apps.public_ids.models import PublicCodeModel

pytestmark = pytest.mark.django_db

Models = tuple[type[PublicCodeModel], type[PublicCodeModel]]


def test_a_new_child_on_an_existing_parent_row_raises(
    parent_and_child: Models,
) -> None:
    par_model, kid_model = parent_and_child
    parent = par_model._default_manager.create(label="made-up one")
    kid = kid_model(par_ptr_id=parent.pk, label="made-up one")

    with pytest.raises(IntegrityError), transaction.atomic():
        kid.save()

    stored = par_model._default_manager.get(pk=parent.pk)
    assert stored.public_code == parent.public_code
    assert kid_model._default_manager.count() == 0
