"""The API's request and response schemas for Matches (issue #31).

A Match in a response names each participant by display name and OPEN
Code, whatever that player's own Privacy Settings. The one exception is a
participant whose Account is inactive: ADR 0002 shows a Player's name only
while their Account is active, so they show as ``PRIVATE_PLAYER_NAME``
with no code, unless the viewer is that participant's own Account.

No schema here carries a row id, the submitter, a flag, or any personal
field other than a display name.
"""

from datetime import date
from typing import TYPE_CHECKING

from django.db.models import Prefetch, QuerySet
from ninja import Schema

from apps.matches.models import (
    BestOf,
    Game,
    GameTarget,
    Match,
    MatchFormat,
    MatchParticipant,
    MatchStatus,
    ScoringType,
    Team,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

PRIVATE_PLAYER_NAME = "Private player"


class GameScoreIn(Schema):
    """One game's score: the points each team won."""

    team_a: int
    team_b: int


class MatchCreateIn(Schema):
    """A player's own match submission.

    The field names are ``validate_match``'s argument names, so its issues
    name the request fields. A missing game target means 11, a missing
    scoring type means side-out, and a missing best-of is inferred from
    the games.
    """

    format: MatchFormat
    played_on: date
    team_a: list[str]
    team_b: list[str]
    games: list[GameScoreIn]
    best_of: BestOf | None = None
    scoring_type: ScoringType | None = None
    game_target: GameTarget | None = None


class ParticipantOut(Schema):
    """A player in a match. ``code`` is null for a Private player."""

    code: str | None
    display_name: str


class GameOut(Schema):
    """One game's number and the points each team won."""

    number: int
    team_a: int
    team_b: int


class MatchOut(Schema):
    """A match, its teams, and its games."""

    code: str
    status: MatchStatus
    format: MatchFormat
    played_on: date
    best_of: BestOf
    scoring_type: ScoringType
    game_target: GameTarget
    team_a: list[ParticipantOut]
    team_b: list[ParticipantOut]
    games: list[GameOut]


def with_match_details(queryset: QuerySet[Match]) -> QuerySet[Match]:
    """Prefetch what ``match_out`` reads, in a fixed number of queries."""
    participants = MatchParticipant.objects.select_related("player__account")
    return queryset.prefetch_related(
        Prefetch("participants", queryset=participants.order_by("pk"))
    ).prefetch_related(Prefetch("games", queryset=Game.objects.order_by("game_number")))


def _participant_out(
    participant: MatchParticipant, viewer: "_User | None"
) -> ParticipantOut:
    player = participant.player
    is_viewer = viewer is not None and viewer.pk == player.account_id
    if not player.account.is_active and not is_viewer:
        return ParticipantOut(code=None, display_name=PRIVATE_PLAYER_NAME)
    return ParticipantOut(code=player.public_code, display_name=player.display_name)


def match_out(match: Match, viewer: "_User | None") -> MatchOut:
    """The response for ``match`` as ``viewer`` sees it.

    Reads the participants, their players and Accounts, and the games, so
    load the match through ``with_match_details`` first.
    """
    participants = list(match.participants.all())
    return MatchOut(
        code=match.public_code,
        status=MatchStatus(match.status),
        format=MatchFormat(match.format),
        played_on=match.played_on,
        best_of=BestOf(match.best_of),
        scoring_type=ScoringType(match.scoring_type),
        game_target=GameTarget(match.game_target),
        team_a=[_participant_out(p, viewer) for p in participants if p.team == Team.A],
        team_b=[_participant_out(p, viewer) for p in participants if p.team == Team.B],
        games=[
            GameOut(number=g.game_number, team_a=g.team_a_score, team_b=g.team_b_score)
            for g in match.games.all()
        ],
    )
