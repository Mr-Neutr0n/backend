"""Factories for Matches, their participants, and their games.

Made-up data only, never real player data.
"""

from datetime import date
from typing import Any

from factory.declarations import LazyFunction, SubFactory, Trait
from factory.django import DjangoModelFactory
from factory.helpers import post_generation
from faker import Faker

from apps.accounts.tests.factories import UserFactory
from apps.matches.models import (
    BestOf,
    Game,
    GameTarget,
    Match,
    MatchFormat,
    MatchParticipant,
    ScoringType,
    Team,
)
from apps.matches.services import match_fingerprint
from apps.partners.tests.factories import PartnerApplicationFactory
from apps.players.tests.factories import PlayerFactory

_faker = Faker()

PLAYERS_PER_TEAM = {MatchFormat.SINGLES: 1, MatchFormat.DOUBLES: 2}


def _played_on() -> date:
    return _faker.date_between(start_date="-1y", end_date="today")


def _external_id() -> str:
    return f"ext-{_faker.uuid4()}"


def _game_winners(best_of: int) -> list[str]:
    """Winners of each game, ending on the game that decides the match."""
    needed = best_of // 2 + 1
    winner = _faker.random_element([Team.A, Team.B])
    loser = Team.B if winner == Team.A else Team.A
    loser_wins = _faker.random_int(min=0, max=needed - 1)
    # The loser's wins fall anywhere before the deciding game.
    earlier = [winner] * (needed - 1) + [loser] * loser_wins
    _faker.random.shuffle(earlier)
    return [*earlier, winner]


class MatchParticipantFactory(DjangoModelFactory[MatchParticipant]):
    """A new Player on team A of a new Match that has no other players."""

    class Meta:
        model = MatchParticipant

    # factory_boy's declarations carry no type hints.
    match = SubFactory(
        "apps.matches.tests.factories.MatchFactory", games=False, participants=False
    )  # type: ignore[no-untyped-call]
    player = SubFactory(PlayerFactory)  # type: ignore[no-untyped-call]
    team = Team.A


class GameFactory(DjangoModelFactory[Game]):
    """Game 1 of a new Match that has no other games, won 11 by team A."""

    class Meta:
        model = Game

    match = SubFactory(
        "apps.matches.tests.factories.MatchFactory", games=False, participants=False
    )  # type: ignore[no-untyped-call]
    game_number = 1
    team_a_score = GameTarget.ELEVEN
    team_b_score = LazyFunction(lambda: _faker.random_int(min=0, max=9))  # type: ignore[no-untyped-call]


class MatchFactory(DjangoModelFactory[Match]):
    """A pending singles Match an Account submitted, best of 1 to 11, side-out.

    It has the players its format needs and games that decide it: each
    game's winner reaches the target and the loser stays at least 2 behind.
    Traits: ``best_of_1``, ``best_of_3``, ``best_of_5``, ``side_out``,
    ``rally``, and ``by_application`` (a Partner Application submitted it,
    with an external ID). Pass ``games=False`` or ``participants=False``
    to leave those out. A match with both gets the fingerprint
    ``record_match`` would give it, so it is found as a duplicate; one
    without either has a blank fingerprint.
    """

    class Meta:
        model = Match
        skip_postgeneration_save = True

    class Params:
        best_of_1 = Trait(best_of=BestOf.ONE)  # type: ignore[no-untyped-call]
        best_of_3 = Trait(best_of=BestOf.THREE)  # type: ignore[no-untyped-call]
        best_of_5 = Trait(best_of=BestOf.FIVE)  # type: ignore[no-untyped-call]
        side_out = Trait(scoring_type=ScoringType.SIDE_OUT)  # type: ignore[no-untyped-call]
        rally = Trait(scoring_type=ScoringType.RALLY)  # type: ignore[no-untyped-call]
        by_application = Trait(  # type: ignore[no-untyped-call]
            submitted_by_user=None,
            submitted_by_application=SubFactory(PartnerApplicationFactory),  # type: ignore[no-untyped-call]
            external_id=LazyFunction(_external_id),  # type: ignore[no-untyped-call]
        )

    format = MatchFormat.SINGLES
    played_on = LazyFunction(_played_on)  # type: ignore[no-untyped-call]
    best_of = BestOf.ONE
    game_target = GameTarget.ELEVEN
    scoring_type = ScoringType.SIDE_OUT
    submitted_by_user = SubFactory(UserFactory)  # type: ignore[no-untyped-call]

    @post_generation  # type: ignore[untyped-decorator]
    def participants(self: Match, create: bool, extracted: Any, **kwargs: Any) -> None:
        if not create or extracted is False:
            return
        for team in Team:
            for _ in range(PLAYERS_PER_TEAM[MatchFormat(self.format)]):
                MatchParticipantFactory.create(match=self, team=team)

    @post_generation  # type: ignore[untyped-decorator]
    def games(self: Match, create: bool, extracted: Any, **kwargs: Any) -> None:
        if not create or extracted is False:
            return
        target = int(self.game_target)
        for number, winner in enumerate(_game_winners(int(self.best_of)), start=1):
            loser_score = _faker.random_int(min=0, max=target - 2)
            a, b = (target, loser_score) if winner == Team.A else (loser_score, target)
            GameFactory.create(
                match=self, game_number=number, team_a_score=a, team_b_score=b
            )

    @post_generation  # type: ignore[untyped-decorator]
    def set_fingerprint(
        self: Match, create: bool, extracted: Any, **kwargs: Any
    ) -> None:
        """Fingerprint a match that has players and games, as record_match does.

        Test setup only, not a ledger edit path. Runs after the participant
        and game hooks. A fingerprint passed to the factory is kept. The
        hook's name differs from the field's, so factory_boy passes that
        value to the model instead of to this hook.
        """
        if not create or self.fingerprint:
            return
        participants = list(self.participants.all())
        games = [(g.team_a_score, g.team_b_score) for g in self.games.all()]
        if not participants or not games:
            return
        teams = {
            team: [p.player_id for p in participants if p.team == team] for team in Team
        }
        self.fingerprint = match_fingerprint(
            teams[Team.A], teams[Team.B], self.played_on, games
        )
        self.save(update_fields=["fingerprint"])


class DoublesMatchFactory(MatchFactory):
    """A MatchFactory match in doubles: two players per team."""

    format = MatchFormat.DOUBLES
