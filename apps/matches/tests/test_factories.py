"""The match factories: team sizes, traits, and games that decide the match."""

import pytest

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
from apps.matches.tests.factories import (
    DoublesMatchFactory,
    GameFactory,
    MatchFactory,
    MatchParticipantFactory,
)

pytestmark = pytest.mark.django_db


def _team_size(match: Match, team: str) -> int:
    return match.participants.filter(team=team).count()


def _decides_the_match(match: Match) -> bool:
    """True when the games decide the match under the engine's rules.

    Each game's winner reaches the target and wins by 2, the winner of the
    match wins a majority of ``best_of``, and no game follows the deciding
    game. A test helper only: the backend does not score matches (#24 calls
    the engine).
    """
    needed = match.best_of // 2 + 1
    wins = {Team.A: 0, Team.B: 0}
    games = list(match.games.order_by("game_number"))
    if [game.game_number for game in games] != list(range(1, len(games) + 1)):
        return False
    for index, game in enumerate(games):
        high = max(game.team_a_score, game.team_b_score)
        low = min(game.team_a_score, game.team_b_score)
        if high < match.game_target or high - low < 2:
            return False
        if high > match.game_target and high - low != 2:
            return False
        wins[Team.A if game.team_a_score > game.team_b_score else Team.B] += 1
        decided = max(wins.values()) == needed
        if decided != (index == len(games) - 1):
            return False
    return max(wins.values()) == needed


def test_match_factory_is_a_pending_singles_match_with_one_player_per_team() -> None:
    match = MatchFactory.create()

    assert match.format == MatchFormat.SINGLES
    assert match.status == MatchStatus.PENDING
    assert _team_size(match, Team.A) == 1
    assert _team_size(match, Team.B) == 1


def test_doubles_factory_has_two_players_per_team() -> None:
    match = DoublesMatchFactory.create()

    assert match.format == MatchFormat.DOUBLES
    assert _team_size(match, Team.A) == 2
    assert _team_size(match, Team.B) == 2


def test_match_factory_defaults() -> None:
    match = MatchFactory.create()

    assert match.best_of == BestOf.ONE
    assert match.game_target == GameTarget.ELEVEN
    assert match.scoring_type == ScoringType.SIDE_OUT
    assert match.submitted_by_user is not None
    assert match.submitted_by_application is None
    assert match.external_id == ""


def test_match_factory_passes_full_clean() -> None:
    MatchFactory.create().full_clean()


@pytest.mark.parametrize(
    ("trait", "best_of"),
    [("best_of_1", 1), ("best_of_3", 3), ("best_of_5", 5)],
)
def test_best_of_traits(trait: str, best_of: int) -> None:
    match = MatchFactory.create(**{trait: True})

    assert match.best_of == best_of


@pytest.mark.parametrize(
    ("trait", "scoring_type"),
    [("side_out", ScoringType.SIDE_OUT), ("rally", ScoringType.RALLY)],
)
def test_scoring_traits(trait: str, scoring_type: str) -> None:
    match = MatchFactory.create(**{trait: True})

    assert match.scoring_type == scoring_type


def test_by_application_trait() -> None:
    match = MatchFactory.create(by_application=True)

    assert match.submitted_by_user is None
    assert match.submitted_by_application is not None
    assert match.external_id
    match.full_clean()


@pytest.mark.parametrize("trait", ["best_of_1", "best_of_3", "best_of_5"])
@pytest.mark.parametrize("target", [11, 15, 21])
def test_factory_games_decide_the_match(trait: str, target: int) -> None:
    for _ in range(3):
        match = DoublesMatchFactory.create(**{trait: True}, game_target=target)

        assert _decides_the_match(match)


def test_best_of_3_and_5_factory_matches_vary_their_game_count() -> None:
    counts = {MatchFactory.create(best_of_5=True).games.count() for _ in range(20)}

    assert len(counts) > 1
    assert counts <= {3, 4, 5}


def test_game_and_participant_factories() -> None:
    match = MatchFactory.create()

    game = GameFactory.create(match=match, game_number=2)
    participant = MatchParticipantFactory.create(match=match, team=Team.A)

    assert Game.objects.filter(match=match, game_number=2).get() == game
    assert MatchParticipant.objects.filter(match=match).count() == 3
    assert participant.player is not None
