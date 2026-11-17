"""The API's Match schema and the Private player rule (issue #31).

A participant shows by display name and OPEN Code, whatever their own
Privacy Settings, except while their Account is inactive: then they show
as "Private player" with no code (ADR 0002), unless the viewer is that
participant's own Account. Made-up data only.
"""

import pytest
from django.contrib.auth import get_user_model
from pytest_django import DjangoAssertNumQueries

from apps.matches.models import Match
from apps.matches.schemas import PRIVATE_PLAYER_NAME, match_out, with_match_details
from apps.matches.tests.conftest import WORKFLOW_GAMES, WORKFLOW_PLAYED_ON
from apps.players.models import Player, PlayerPrivacy, Visibility

pytestmark = pytest.mark.django_db


def _loaded(match: Match) -> Match:
    return with_match_details(Match.objects.filter(pk=match.pk)).get()


def test_match_out_lists_teams_games_and_settings(
    pending: Match, players: list[Player]
) -> None:
    out = match_out(_loaded(pending), players[0].account)

    assert out.model_dump() == {
        "code": pending.public_code,
        "status": "pending",
        "format": "doubles",
        "played_on": WORKFLOW_PLAYED_ON,
        "best_of": 3,
        "scoring_type": "side_out",
        "game_target": 11,
        "team_a": [
            {"code": p.public_code, "display_name": p.display_name} for p in players[:2]
        ],
        "team_b": [
            {"code": p.public_code, "display_name": p.display_name} for p in players[2:]
        ],
        "games": [
            {"number": number, "team_a": a, "team_b": b}
            for number, (a, b) in enumerate(WORKFLOW_GAMES, start=1)
        ],
    }


def test_inactive_participant_shows_as_private_player_to_others(
    pending: Match, players: list[Player]
) -> None:
    get_user_model().objects.filter(pk=players[3].account_id).update(is_active=False)

    out = match_out(_loaded(pending), players[0].account)

    assert out.team_b[1].model_dump() == {
        "code": None,
        "display_name": PRIVATE_PLAYER_NAME,
    }
    assert PRIVATE_PLAYER_NAME == "Private player"
    assert players[3].display_name not in out.model_dump_json()
    assert players[3].public_code not in out.model_dump_json()
    # Everyone else still shows by name.
    assert out.team_b[0].display_name == players[2].display_name


def test_inactive_participant_sees_their_own_name(
    pending: Match, players: list[Player]
) -> None:
    get_user_model().objects.filter(pk=players[3].account_id).update(is_active=False)
    viewer = get_user_model().objects.get(pk=players[3].account_id)

    out = match_out(_loaded(pending), viewer)

    assert out.team_b[1].model_dump() == {
        "code": players[3].public_code,
        "display_name": players[3].display_name,
    }


def test_private_privacy_settings_do_not_hide_a_participant(
    pending: Match, players: list[Player]
) -> None:
    PlayerPrivacy.objects.filter(player=players[2]).update(
        match_history_visibility=Visibility.PRIVATE
    )

    out = match_out(_loaded(pending), players[0].account)

    assert out.team_b[0].code == players[2].public_code
    assert out.team_b[0].display_name == players[2].display_name


def test_match_out_reads_only_prefetched_rows(
    pending: Match,
    players: list[Player],
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    loaded = _loaded(pending)

    with django_assert_num_queries(0):
        match_out(loaded, players[0].account)
