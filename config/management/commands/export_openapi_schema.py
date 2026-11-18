"""Write the checked-in OpenAPI document for the frontend client (#42)."""

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from config.api import api

SCHEMA_PATH = Path("openapi") / "openapi.json"


def render_openapi_schema() -> str:
    """Return the schema in its committed form.

    Sorting keys and ending with one newline make repeat runs byte-for-byte
    identical, so a pull request shows only real API changes.
    """
    return json.dumps(api.get_openapi_schema(), indent=2, sort_keys=True) + "\n"


class Command(BaseCommand):
    help = "Write openapi/openapi.json from the current API."

    def handle(self, *args: Any, **options: Any) -> None:
        path = Path(settings.BASE_DIR) / SCHEMA_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_openapi_schema(), encoding="utf-8")
        self.stdout.write(f"Wrote {SCHEMA_PATH}")
