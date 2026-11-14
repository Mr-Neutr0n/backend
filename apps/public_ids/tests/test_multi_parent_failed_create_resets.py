"""A failed create of a model with two concrete parents resets every link."""

from collections.abc import Iterator

import pytest
from django.db import IntegrityError, connection, models
from django.test.utils import isolate_apps

from apps.public_ids.codes import CodeType
from apps.public_ids.models import PublicCodeModel

pytestmark = pytest.mark.django_db


@pytest.fixture
def multi_model(db: None) -> Iterator[type[PublicCodeModel]]:
    """``Multi(Par, Other)``: a coded parent, a plain parent, and its tables."""
    with isolate_apps("apps.public_ids"):

        class Par(PublicCodeModel):
            public_code_type = CodeType.CLUB
            label = models.CharField(max_length=50, unique=True)

            class Meta:
                app_label = "public_ids"

            def __str__(self) -> str:
                return self.label

        class Other(models.Model):
            other_id = models.AutoField(primary_key=True)
            note = models.CharField(max_length=50, blank=True)

            class Meta:
                app_label = "public_ids"

            def __str__(self) -> str:
                return self.note

        class Multi(Par, Other):
            nickname = models.CharField(max_length=50, unique=True)

            class Meta:
                app_label = "public_ids"

        with connection.schema_editor() as editor:
            editor.create_model(Par)
            editor.create_model(Other)
            editor.create_model(Multi)
        yield Multi


def test_a_failed_create_resets_every_parent_link(
    multi_model: type[PublicCodeModel],
) -> None:
    multi_model._default_manager.create(label="made-up one", nickname="same")
    multi = multi_model(label="made-up two", nickname="same")

    # Both parent rows insert, then Multi's own row fails on its nickname.
    with pytest.raises(IntegrityError):
        multi.save()

    keys = ("pk", "id", "other_id", "par_ptr_id", "other_ptr_id")
    assert {name: getattr(multi, name) for name in keys} == dict.fromkeys(keys)
    assert multi.public_code is None
    assert multi._state.adding is True

    multi.nickname = "different"
    multi.save()

    assert multi_model._default_manager.filter(pk=multi.pk).exists()
