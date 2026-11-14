"""A code a parent-only row holds is a collision for a new child."""

import pytest

from apps.public_ids import codes
from apps.public_ids.codes import CodeType
from apps.public_ids.models import IssuedCode, PublicCodeModel

pytestmark = pytest.mark.django_db

Models = tuple[type[PublicCodeModel], type[PublicCodeModel]]


def test_a_code_held_by_a_parent_only_row_is_retried(
    parent_and_child: Models, monkeypatch: pytest.MonkeyPatch
) -> None:
    par_model, kid_model = parent_and_child
    taken = codes.generate(CodeType.PLAYER)
    fresh = codes.generate(CodeType.PLAYER)
    # bulk_create skips save(), so this code never reaches the registry.
    par_model._default_manager.bulk_create(
        [par_model(label="made-up one", public_code=taken)]
    )
    assert not IssuedCode.objects.filter(code=taken).exists()
    sequence = iter([taken, fresh])
    monkeypatch.setattr(
        "apps.public_ids.models._generate", lambda code_type: next(sequence)
    )

    kid = kid_model._default_manager.create(label="made-up two")

    assert kid.public_code == fresh
