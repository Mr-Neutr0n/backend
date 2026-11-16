"""A ``DuplicateMatchError`` raised in an operation returns 409 with an
``ErrorResponse`` that names the earlier match's OPEN code."""

import uuid

import pytest
from django.http import HttpRequest
from ninja.testing import TestClient

from apps.matches.services import DuplicateKind, DuplicateMatchError
from config.api import OpenNinjaAPI
from config.api_errors import ErrorResponse

EXISTING_CODE = "M-0000-0000-0000"


def _client(kind: DuplicateKind) -> TestClient:
    """An API with one test-only operation, never mounted in the URLconf."""
    api = OpenNinjaAPI(urls_namespace=f"test-{uuid.uuid4().hex}")

    @api.post("/matches", operation_id="submit_duplicate")
    def submit_duplicate(request: HttpRequest) -> None:
        raise DuplicateMatchError(kind, EXISTING_CODE)

    return TestClient(api)


@pytest.mark.parametrize(
    ("kind", "field", "message"),
    [
        (
            DuplicateKind.DUPLICATE_MATCH,
            "match",
            f"This match was already submitted as {EXISTING_CODE}.",
        ),
        (
            DuplicateKind.DUPLICATE_EXTERNAL_ID,
            "external_id",
            "This application already submitted a match with this external ID: "
            f"{EXISTING_CODE}.",
        ),
    ],
)
def test_duplicate_match_error_returns_409(
    kind: DuplicateKind, field: str, message: str
) -> None:
    response = _client(kind).post("/matches")

    assert response.status_code == 409
    content = response.json()
    assert set(content) == {"code", "message", "errors"}
    body = ErrorResponse.model_validate(content)
    assert body.code == "duplicate_match"
    assert body.message == message
    assert [error.model_dump() for error in body.errors] == [
        {"field": field, "code": kind.value, "message": message}
    ]
