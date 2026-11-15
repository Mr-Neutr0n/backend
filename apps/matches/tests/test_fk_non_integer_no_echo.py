"""A non-integer id on a link is refused without repeating it.

``ForeignKey.to_python`` uses the target's primary key field, whose
``invalid`` message repeats the submitted value, so the link's own message
override does not cover it (CLAUDE.md, API).
"""

from datetime import date
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import models

from apps.matches.models import BestOf, Game, Match, MatchFormat, MatchParticipant, Team

pytestmark = pytest.mark.django_db

MARKER = "zqxjmarker"


def _messages(error: ValidationError) -> str:
    return " ".join(
        message for messages in error.message_dict.values() for message in messages
    )


def _match(**links: Any) -> Match:
    return Match(
        format=MatchFormat.SINGLES,
        played_on=date(2026, 6, 1),
        best_of=BestOf.ONE,
        **links,
    )


def _participant(**links: Any) -> MatchParticipant:
    return MatchParticipant(team=Team.A, **links)


def _game(**links: Any) -> Game:
    return Game(game_number=1, team_a_score=11, team_b_score=5, **links)


@pytest.mark.parametrize(
    ("build", "field"),
    [
        (_match, "event"),
        (_match, "club"),
        (_match, "submitted_by_user"),
        (_match, "submitted_by_application"),
        (_participant, "match"),
        (_participant, "player"),
        (_game, "match"),
    ],
)
def test_non_integer_link_is_refused_without_the_value(build: Any, field: str) -> None:
    instance: models.Model = build(**{f"{field}_id": MARKER})

    with pytest.raises(ValidationError) as error:
        instance.full_clean()

    assert field in error.value.message_dict
    assert MARKER not in _messages(error.value)
