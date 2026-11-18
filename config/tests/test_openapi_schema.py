"""The checked-in OpenAPI document (issue #42)."""

import json
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.core.management import call_command
from django.test import Client

from config.management.commands.export_openapi_schema import (
    SCHEMA_PATH,
    render_openapi_schema,
)


def test_generated_schema_matches_served_api() -> None:
    document = json.loads(render_openapi_schema())
    response = Client().get("/api/v1/openapi.json")

    assert response.status_code == 200
    assert document == response.json()


def test_committed_schema_is_current() -> None:
    path = Path(django_settings.BASE_DIR) / SCHEMA_PATH

    assert path.read_text(encoding="utf-8") == render_openapi_schema()


def test_schema_is_deterministic() -> None:
    assert render_openapi_schema() == render_openapi_schema()


def test_command_writes_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(django_settings, "BASE_DIR", tmp_path)

    call_command("export_openapi_schema")

    assert (tmp_path / SCHEMA_PATH).read_text(encoding="utf-8") == (
        render_openapi_schema()
    )
