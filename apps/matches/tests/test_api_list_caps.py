"""Submission lists have generous caps with fixed messages (issue #31).

Without a cap, a body near the upload limit makes the view normalize tens
of thousands of codes and build one huge lookup. The caps (10 players a
team, 20 games) sit well above what ``validate_match`` allows, so an
ordinary mistake still gets its friendlier message. A refused list
gets fixed text that never repeats a submitted value or the list's
length. Made-up data only.
"""

from typing import Any

import pytest
from django.test import Client

from apps.matches.models import Match
from apps.players.models import Player
from apps.players.tests.factories import PlayerFactory

pytestmark = pytest.mark.django_db

MATCHES = "/api/v1/matches/"
TEAM_MESSAGE = "Enter at most 10 players for a team."
GAMES_MESSAGE = "Enter at most 20 games."


@pytest.fixture
def players() -> list[Player]:
    return [PlayerFactory.create() for _ in range(2)]


def _submit(players: list[Player], **overrides: Any) -> Any:
    body: dict[str, Any] = {
        "format": "singles",
        "played_on": "2026-06-01",
        "team_a": [players[0].public_code],
        "team_b": [players[1].public_code],
        "games": [{"team_a": 11, "team_b": 4}],
    }
    body.update(overrides)
    client = Client()
    client.force_login(players[0].account)
    return client.post(MATCHES, body, content_type="application/json")


def _errors(response: Any) -> list[tuple[str, str, str]]:
    return [
        (error["field"], error["code"], error["message"])
        for error in response.json()["errors"]
    ]


@pytest.mark.parametrize("team", ["team_a", "team_b"])
@pytest.mark.parametrize("size", [11, 5000])
def test_too_many_players_on_a_team_gets_a_fixed_422(
    players: list[Player], team: str, size: int
) -> None:
    codes = [players[0].public_code] * size

    response = _submit(players, **{team: codes})

    assert response.status_code == 422
    assert _errors(response) == [(f"body.{team}", "too_long", TEAM_MESSAGE)]
    assert str(size) not in response.content.decode()
    assert not Match.objects.exists()


@pytest.mark.parametrize("size", [21, 5000])
def test_too_many_games_gets_a_fixed_422(players: list[Player], size: int) -> None:
    games = [{"team_a": 11, "team_b": 4}] * size

    response = _submit(players, games=games)

    assert response.status_code == 422
    assert _errors(response) == [("body.games", "too_long", GAMES_MESSAGE)]
    assert str(size) not in response.content.decode()
    assert not Match.objects.exists()


def test_ten_players_reach_the_score_rules(players: list[Player]) -> None:
    response = _submit(players, team_a=[players[0].public_code] * 10)

    assert response.status_code == 422
    assert ("body.team_a", "team_size") in {
        (field, code) for field, code, _message in _errors(response)
    }


def test_twenty_games_reach_the_score_rules(players: list[Player]) -> None:
    response = _submit(players, games=[{"team_a": 11, "team_b": 4}] * 20)

    assert response.status_code == 422
    assert "too_long" not in {code for _field, code, _message in _errors(response)}


def test_caps_are_documented() -> None:
    document = Client().get("/api/v1/openapi.json").json()
    operation = document["paths"][MATCHES]["post"]
    ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    properties = document["components"]["schemas"][ref.rsplit("/", 1)[1]]["properties"]

    assert properties["team_a"]["maxItems"] == 10
    assert properties["team_b"]["maxItems"] == 10
    assert properties["games"]["maxItems"] == 20
