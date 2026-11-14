"""A code a record holds without a registry row is still a collision."""

import pytest

from apps.public_ids import codes
from apps.public_ids.codes import CodeType
from apps.public_ids.models import IssuedCode, PublicCodeModel

pytestmark = pytest.mark.django_db


def test_a_code_held_outside_the_registry_is_retried(
    thing_model: type[PublicCodeModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    taken = codes.generate(CodeType.PLAYER)
    fresh = codes.generate(CodeType.PLAYER)
    # bulk_create skips save(), so this code never reaches the registry.
    thing_model._default_manager.bulk_create(
        [thing_model(label="made-up one", public_code=taken)]
    )
    assert not IssuedCode.objects.filter(code=taken).exists()
    sequence = iter([taken, fresh])
    monkeypatch.setattr(
        "apps.public_ids.models._generate", lambda code_type: next(sequence)
    )

    thing = thing_model._default_manager.create(label="made-up two")

    assert thing.public_code == fresh
