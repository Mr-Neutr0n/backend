"""Match errors raised in an operation come back as an ``ErrorResponse``
(issue #31): ``MatchValidationError`` as 422 with one item per issue,
``MatchActionDenied`` as 403, and ``MatchStateError`` as 409, each with
fixed text."""

import uuid

from django.http import HttpRequest
from ninja.testing import TestClient

from apps.matches.permissions import MatchActionDenied
from apps.matches.services import MatchIssue, MatchValidationError
from apps.matches.workflow import MatchStateError
from config.api import OpenNinjaAPI
from config.api_errors import ErrorResponse


def _client(exc: Exception) -> TestClient:
    """An API with one test-only operation, never mounted in the URLconf."""
    api = OpenNinjaAPI(urls_namespace=f"test-{uuid.uuid4().hex}")

    @api.post("/matches", operation_id="raise_match_error")
    def raise_match_error(request: HttpRequest) -> None:
        raise exc

    return TestClient(api)


def test_match_validation_error_returns_422_with_one_item_per_issue() -> None:
    issues = [
        MatchIssue("games.0", "tie", "Game 1 cannot end in a tie."),
        MatchIssue("team_b", "team_size", "Team B must have 2 players in doubles."),
    ]

    response = _client(MatchValidationError(issues)).post("/matches")

    assert response.status_code == 422
    content = response.json()
    assert set(content) == {"code", "message", "errors"}
    assert content == {
        "code": "validation_error",
        "message": "The request is not valid.",
        "errors": [
            {
                "field": "games.0",
                "code": "tie",
                "message": "Game 1 cannot end in a tie.",
            },
            {
                "field": "team_b",
                "code": "team_size",
                "message": "Team B must have 2 players in doubles.",
            },
        ],
    }


def test_match_action_denied_returns_403_with_fixed_text() -> None:
    response = _client(MatchActionDenied()).post("/matches")

    assert response.status_code == 403
    body = ErrorResponse.model_validate(response.json())
    assert body.code == "forbidden"
    assert body.message == "You are not allowed to change this match."
    assert body.errors == []


def test_match_state_error_returns_409_conflict_with_fixed_text() -> None:
    response = _client(MatchStateError()).post("/matches")

    assert response.status_code == 409
    body = ErrorResponse.model_validate(response.json())
    assert body.code == "conflict"
    assert body.message == ("This match cannot make this change in its current status.")
    assert body.errors == []
