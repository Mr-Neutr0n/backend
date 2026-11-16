"""A ``MatchPermissionDenied`` raised in an operation returns 403 with an
``ErrorResponse`` of fixed text that never says which rule failed (#79)."""

import uuid

from django.http import HttpRequest
from ninja.testing import TestClient

from apps.matches.permissions import MatchPermissionDenied
from config.api import OpenNinjaAPI
from config.api_errors import ErrorResponse


def _client() -> TestClient:
    """An API with one test-only operation, never mounted in the URLconf."""
    api = OpenNinjaAPI(urls_namespace=f"test-{uuid.uuid4().hex}")

    @api.post("/matches", operation_id="submit_refused")
    def submit_refused(request: HttpRequest) -> None:
        raise MatchPermissionDenied

    return TestClient(api)


def test_match_permission_denied_returns_403_with_fixed_text() -> None:
    response = _client().post("/matches")

    assert response.status_code == 403
    content = response.json()
    assert set(content) == {"code", "message", "errors"}
    body = ErrorResponse.model_validate(content)
    assert body.code == "forbidden"
    assert body.message == "You are not allowed to submit this match."
    assert body.errors == []
