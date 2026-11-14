"""A save whose transaction fails on exit leaves the instance ready to retry."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from django.db import OperationalError, transaction

from apps.public_ids.models import IssuedCode, PublicCodeModel

pytestmark = pytest.mark.django_db


def _fail_first_atomic_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the first atomic block roll back and raise as it exits cleanly.

    This stands in for a commit that fails. Later blocks behave normally.
    """
    real_atomic = transaction.atomic
    state = {"calls": 0}

    @contextmanager
    def atomic(*args: Any, **kwargs: Any) -> Iterator[None]:
        state["calls"] += 1
        first = state["calls"] == 1
        block = real_atomic(*args, **kwargs)
        block.__enter__()
        try:
            yield
        except BaseException as exc:
            block.__exit__(type(exc), exc, exc.__traceback__)
            raise
        if first:
            error = OperationalError("Made-up commit failure.")
            block.__exit__(OperationalError, error, None)
            raise error
        block.__exit__(None, None, None)

    monkeypatch.setattr("apps.public_ids.models.transaction.atomic", atomic)


def test_a_failed_commit_lets_a_retry_issue_a_fresh_code(
    thing_model: type[PublicCodeModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_first_atomic_on_exit(monkeypatch)
    thing = thing_model(label="made-up one")

    with pytest.raises(OperationalError):
        thing.save()

    assert thing.public_code is None
    assert thing._state.adding is True
    assert thing.pk is None
    assert thing_model._default_manager.count() == 0
    assert IssuedCode.objects.count() == 0

    thing.save()

    stored = thing_model._default_manager.get(pk=thing.pk)
    assert stored.public_code == thing.public_code
    assert IssuedCode.objects.filter(code=thing.public_code).exists()
