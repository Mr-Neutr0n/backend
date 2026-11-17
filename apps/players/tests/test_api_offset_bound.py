"""The match history's offset has an upper bound (issue #31).

Postgres takes a bigint OFFSET. A larger offset must be refused as a 422
``ErrorResponse`` before it reaches the database, never a 500. Made-up
data only.
"""

from typing import Any

import pytest
from django.test import Client

from apps.players.tests.factories import PlayerFactory

pytestmark = pytest.mark.django_db

MAX_OFFSET = 2**63 - 1


def _history(offset: int) -> Any:
    player = PlayerFactory.create()
    client = Client(raise_request_exception=False)
    client.force_login(player.account)
    return client.get(
        f"/api/v1/players/{player.public_code}/matches", {"offset": offset}
    )


def test_offset_past_bigint_gets_422() -> None:
    response = _history(MAX_OFFSET + 1)

    assert response.status_code == 422
    content = response.json()
    assert content["code"] == "validation_error"
    assert [error["field"] for error in content["errors"]] == ["query.offset"]
    assert str(MAX_OFFSET + 1) not in response.content.decode()


def test_largest_offset_returns_an_empty_page() -> None:
    response = _history(MAX_OFFSET)

    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}


def test_offset_bound_is_documented() -> None:
    document = Client().get("/api/v1/openapi.json").json()
    parameters = document["paths"]["/api/v1/players/{code}/matches"]["get"][
        "parameters"
    ]
    offset = next(p["schema"] for p in parameters if p["name"] == "offset")

    assert (offset["minimum"], offset["maximum"]) == (0, MAX_OFFSET)
