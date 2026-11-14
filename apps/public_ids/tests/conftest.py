"""A throwaway model with a public code, for the public_ids tests.

No real model with a public code exists yet, so the tests use ``Thing``.
It lives in an isolated app registry, so ``makemigrations`` never sees it.
Its table is created inside the test transaction and rolls back with it.
"""

from collections.abc import Iterator

import pytest
from django.db import connection, models
from django.test.utils import isolate_apps

from apps.public_ids.codes import CodeType
from apps.public_ids.models import PublicCodeModel


@pytest.fixture
def thing_model(db: None) -> Iterator[type[PublicCodeModel]]:
    """A concrete player-coded model with a unique ``label``, and its table."""
    with isolate_apps("apps.public_ids"):

        class Thing(PublicCodeModel):
            public_code_type = CodeType.PLAYER
            label = models.CharField(max_length=50, unique=True)

            class Meta:
                app_label = "public_ids"

            def __str__(self) -> str:
                return self.label

        with connection.schema_editor() as editor:
            editor.create_model(Thing)
        yield Thing


@pytest.fixture
def parent_and_child(
    db: None,
) -> Iterator[tuple[type[PublicCodeModel], type[PublicCodeModel]]]:
    """A concrete coded parent and a multi-table child, with their tables.

    The parent holds ``public_code`` and a unique ``label``. The child adds
    a unique ``nickname`` in its own table.
    """
    with isolate_apps("apps.public_ids"):

        class Par(PublicCodeModel):
            public_code_type = CodeType.PLAYER
            label = models.CharField(max_length=50, unique=True)

            class Meta:
                app_label = "public_ids"

            def __str__(self) -> str:
                return self.label

        class Kid(Par):
            nickname = models.CharField(max_length=50, unique=True, blank=True)

            class Meta:
                app_label = "public_ids"

        with connection.schema_editor() as editor:
            editor.create_model(Par)
            editor.create_model(Kid)
        yield Par, Kid
