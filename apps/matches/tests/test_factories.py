"""The match factories: team sizes, traits, and games that decide the match."""

import pytest

from apps.accounts.tests.factories import UserFactory
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
from apps.matches.services import DuplicateMatchError, match_fingerprint, record_match
from apps.matches.tests.factories import (
    DoublesMatchFactory,
    GameFactory,
    MatchFactory,
    MatchParticipantFactory,
)
from apps.players.models import Player

pytestmark = pytest.mark.django_db


def _team_size(match: Match, team: str) -> int:
    return match.participants.filter(team=team).count()


def _decides_the_match(match: Match) -> bool:
    """True when the games decide the match.

    Each game's winner reaches the target and wins by 2, the winner of the
    match wins a majority of ``best_of``, and no game follows the deciding
    game. It mirrors the rules in ``apps.matches.services.validate_match``,
    written out apart so a mistake in one does not hide in the other.
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


def _submission(
    match: Match,
) -> tuple[list[Player], list[Player], list[tuple[int, int]]]:
    """The match's teams and games as record_match takes them."""
    team_a = [p.player for p in match.participants.filter(team=Team.A)]
    team_b = [p.player for p in match.participants.filter(team=Team.B)]
    games = [(g.team_a_score, g.team_b_score) for g in match.games.all()]
    return team_a, team_b, games


@pytest.mark.parametrize("factory", [MatchFactory, DoublesMatchFactory])
def test_factory_sets_the_fingerprint_record_match_would(
    factory: type[MatchFactory],
) -> None:
    match = factory.create(best_of_3=True)
    match.refresh_from_db()
    team_a, team_b, games = _submission(match)

    assert match.fingerprint == match_fingerprint(
        [p.pk for p in team_a], [p.pk for p in team_b], match.played_on, games
    )


def test_factory_match_is_found_as_a_duplicate() -> None:
    match = DoublesMatchFactory.create(best_of_3=True)
    team_a, team_b, games = _submission(match)

    with pytest.raises(DuplicateMatchError) as error:
        record_match(
            format=match.format,
            team_a=team_a,
            team_b=team_b,
            games=games,
            played_on=match.played_on,
            submitted_by_user=UserFactory.create(),
        )

    assert error.value.existing_code == match.public_code


@pytest.mark.parametrize("left_out", ["games", "participants"])
def test_factory_match_without_games_or_players_has_no_fingerprint(
    left_out: str,
) -> None:
    match = MatchFactory.create(**{left_out: False})
    match.refresh_from_db()

    assert match.fingerprint == ""
