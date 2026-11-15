"""Score validation: the rules every match submission must pass.

Every path that submits a Match (the results API, CSV upload, organizer
tools, partner imports) calls ``validate_match`` before it writes anything,
so an impossible score never reaches the ledger (CLAUDE.md, hard rule 3).
The function takes plain values and does no database access.

Players are any hashable reference, since each path resolves players its
own way, but each player must be given as exactly one canonical reference:
a resolved Player, or an OPEN Code already passed through
``apps.public_ids.codes.normalize()``. Never pass raw input. Every
reference in one call must be the same kind (the same type): a call that
mixes kinds is refused with ``mixed_player_references``. The duplicate and
both-teams checks compare references by equality, so two spellings of one
code, or a Player and its code, would count as two players. Teams and the game list are lists or
tuples; anything else (a string, a generator, a dict) is an issue.

Defaults: a missing game target means 11 and a missing scoring type means
side-out. A missing best-of is inferred by ``infer_best_of``: the smallest
allowed best-of whose winning number of games the last game reaches, with
no game after it. Scoring type changes no rule: a game is won at the
target by 2 or more, or past the target by exactly 2.

A failure raises one ``MatchValidationError`` with every issue found. Each
issue has a field, a code, and a message, the shape of the API's
``FieldError``. Messages are fixed text, game numbers, and allowed values,
never a submitted value (CLAUDE.md, API).

No rule reads payment status or any paid entitlement: the function takes
no such input (CLAUDE.md, hard rule 7).
"""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TypeGuard

from django.utils import timezone

from apps.matches.models import (
    MAX_GAMES,
    MAX_UTC_OFFSET_MINUTES,
    BestOf,
    GameTarget,
    MatchFormat,
    ScoringType,
    Team,
)

PLAYERS_PER_TEAM: dict[MatchFormat, int] = {
    MatchFormat.SINGLES: 1,
    MatchFormat.DOUBLES: 2,
}
WIN_MARGIN = 2


@dataclass(frozen=True)
class MatchIssue:
    """One problem with a submission.

    ``field`` is ``format``, ``team_a``, ``team_b``, ``games``,
    ``games.<i>`` (0-based), ``played_on``, ``best_of``, ``game_target``, or
    ``scoring_type``.
    """

    field: str
    code: str
    message: str


class MatchValidationError(Exception):
    """A submission broke one or more rules. ``issues`` is never empty."""

    def __init__(self, issues: Sequence[MatchIssue]) -> None:
        super().__init__("The match is not valid.")
        self.issues: tuple[MatchIssue, ...] = tuple(issues)


@dataclass(frozen=True)
class ValidatedMatch:
    """A submission that passed, with the defaults and inference applied."""

    format: MatchFormat
    team_a: tuple[Hashable, ...]
    team_b: tuple[Hashable, ...]
    games: tuple[tuple[int, int], ...]
    played_on: date
    best_of: BestOf
    game_target: GameTarget
    scoring_type: ScoringType


def _or_list(items: Sequence[object]) -> str:
    words = [str(item) for item in items]
    if len(words) <= 2:
        return " or ".join(words)
    return f"{', '.join(words[:-1])}, or {words[-1]}"


def _labels(choices: Sequence[str]) -> str:
    return _or_list([label.lower() for label in choices])


_FORMAT_CHOICE = f"Choose a format of {_labels(MatchFormat.labels)}."
_SCORING_CHOICE = f"Choose a scoring type of {_labels(ScoringType.labels)}."
_TARGET_CHOICE = f"Choose a game target of {_or_list(GameTarget.values)}."
_BEST_OF_CHOICE = f"Choose a best-of of {_or_list(BestOf.values)}."
_CANNOT_INFER = f"The games do not decide a best of {_or_list(BestOf.values)} match."


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _deciding_game(winners: Sequence[Team], best_of: int) -> int | None:
    """The index of the game that decides the match, or None if none does."""
    needed = best_of // 2 + 1
    wins = {Team.A: 0, Team.B: 0}
    for index, winner in enumerate(winners):
        wins[winner] += 1
        if wins[winner] == needed:
            return index
    return None


def infer_best_of(winners: Sequence[Team]) -> BestOf | None:
    """The smallest best-of the games decide, with no game after the decision.

    ``winners`` is each game's winning team in order. Returns None when no
    allowed best-of fits.
    """
    if not winners:
        return None
    for best_of in sorted(BestOf):
        if _deciding_game(winners, best_of) == len(winners) - 1:
            return best_of
    return None


def _team_players(
    field: str, label: str, team: object
) -> tuple[MatchIssue | None, tuple[Hashable, ...] | None]:
    """A team's players, or the issue that makes them unusable.

    A team is a list or tuple. A string or bytes is refused, not read one
    player per character. Each player is hashable and not None.
    """
    if not isinstance(team, list | tuple):
        return MatchIssue(
            field, "invalid", f"Enter {label} as a list of players."
        ), None
    for player in team:
        try:
            hash(player)
        except TypeError:
            player = None
        if player is None:
            return MatchIssue(
                field, "invalid_player", f"{label} lists a player that is not valid."
            ), None
    return None, tuple(team)


def _team_issues(
    match_format: MatchFormat | None, team_a: object, team_b: object
) -> tuple[list[MatchIssue], tuple[Hashable, ...] | None, tuple[Hashable, ...] | None]:
    """Check both teams. Returns the issues and each usable team, or None."""
    issues: list[MatchIssue] = []
    teams = (("team_a", "Team A", team_a), ("team_b", "Team B", team_b))
    players: dict[str, tuple[Hashable, ...] | None] = {}
    for field, label, team in teams:
        issue, players[field] = _team_players(field, label, team)
        if issue is not None:
            issues.append(issue)
    a, b = players["team_a"], players["team_b"]
    # A Player never equals its code, so the equality checks below cannot
    # be trusted unless every reference is the same kind.
    mixed = (
        a is not None
        and b is not None
        and len({type(player) for player in (*a, *b)}) > 1
    )

    for field, label, _team in teams:
        members = players[field]
        if members is None:
            continue
        if match_format is not None:
            size = PLAYERS_PER_TEAM[match_format]
            if len(members) != size:
                noun = "player" if size == 1 else "players"
                issues.append(
                    MatchIssue(
                        field,
                        "team_size",
                        f"{label} must have {size} {noun} in "
                        f"{match_format.label.lower()}.",
                    )
                )
        if not mixed and len(set(members)) != len(members):
            issues.append(
                MatchIssue(
                    field, "duplicate_player", f"{label} lists a player more than once."
                )
            )
    if mixed:
        issues.append(
            MatchIssue(
                "team_b",
                "mixed_player_references",
                "Give every player the same kind of reference.",
            )
        )
    elif a is not None and b is not None and set(a) & set(b):
        issues.append(
            MatchIssue(
                "team_b", "player_on_both_teams", "A player cannot be on both teams."
            )
        )
    return issues, a, b


def _game_issue(
    index: int, game: object, target: GameTarget | None
) -> tuple[MatchIssue | None, tuple[int, int] | None]:
    """Check one game. Returns its issue, or None and its scores."""
    field = f"games.{index}"
    number = index + 1
    if not isinstance(game, tuple | list) or len(game) != 2:
        return MatchIssue(
            field, "invalid_score", f"Game {number}: enter two scores as whole numbers."
        ), None
    a, b = game
    if not (_is_int(a) and _is_int(b)):
        return MatchIssue(
            field,
            "invalid_score",
            f"Game {number}: enter each score as a whole number.",
        ), None
    if a < 0 or b < 0:
        return MatchIssue(
            field, "negative_score", f"Game {number}: scores cannot be negative."
        ), None
    if a == b:
        return MatchIssue(field, "tie", f"Game {number} cannot end in a tie."), None
    if target is not None:
        high, low = max(a, b), min(a, b)
        if high < target:
            return MatchIssue(
                field,
                "target_not_reached",
                f"Game {number}: the winner must reach the game target.",
            ), None
        if high == target and high - low < WIN_MARGIN:
            return MatchIssue(
                field,
                "not_won_by_two",
                f"Game {number}: the winner must win by {WIN_MARGIN} points.",
            ), None
        if high > target and high - low != WIN_MARGIN:
            return MatchIssue(
                field,
                "played_past_target",
                f"Game {number}: a game played past the target ends when one "
                f"team leads by {WIN_MARGIN}.",
            ), None
    return None, (a, b)


def _played_on_issue(played_on: object) -> MatchIssue | None:
    if not isinstance(played_on, date) or isinstance(played_on, datetime):
        return MatchIssue("played_on", "invalid", "Enter the date played as a date.")
    # The latest local date anywhere on Earth right now.
    latest = (
        timezone.now().astimezone(UTC) + timedelta(minutes=MAX_UTC_OFFSET_MINUTES)
    ).date()
    if played_on > latest:
        return MatchIssue(
            "played_on", "future_date", "The date played cannot be in the future."
        )
    return None


def validate_match(
    *,
    format: str,
    team_a: Sequence[Hashable],
    team_b: Sequence[Hashable],
    games: Sequence[tuple[int, int]],
    played_on: date,
    best_of: int | None = None,
    game_target: int | None = None,
    scoring_type: str | None = None,
) -> ValidatedMatch:
    """Check a submitted match against every rule and return it with defaults.

    Raises ``MatchValidationError`` with every issue found.
    """
    issues: list[MatchIssue] = []

    match_format: MatchFormat | None = None
    if format in MatchFormat.values:
        match_format = MatchFormat(format)
    else:
        issues.append(MatchIssue("format", "invalid_choice", _FORMAT_CHOICE))
    team_issues, players_a, players_b = _team_issues(match_format, team_a, team_b)
    issues.extend(team_issues)

    scoring: ScoringType | None = ScoringType.SIDE_OUT
    if scoring_type is not None:
        if isinstance(scoring_type, str) and scoring_type in ScoringType.values:
            scoring = ScoringType(scoring_type)
        else:
            scoring = None
            issues.append(MatchIssue("scoring_type", "invalid_choice", _SCORING_CHOICE))

    target: GameTarget | None = GameTarget.ELEVEN
    if game_target is not None:
        if _is_int(game_target) and game_target in GameTarget.values:
            target = GameTarget(game_target)
        else:
            target = None
            issues.append(MatchIssue("game_target", "invalid_choice", _TARGET_CHOICE))

    chosen_best_of: BestOf | None = None
    best_of_valid = True
    if best_of is not None:
        if _is_int(best_of) and best_of in BestOf.values:
            chosen_best_of = BestOf(best_of)
        else:
            best_of_valid = False
            issues.append(MatchIssue("best_of", "invalid_choice", _BEST_OF_CHOICE))

    scores: list[tuple[int, int]] = []
    games_valid = True
    if not isinstance(games, list | tuple):
        # A string, a generator, or a dict is not read as games.
        games_valid = False
        issues.append(
            MatchIssue("games", "invalid", "Enter the games as a list of scores.")
        )
    elif len(games) == 0:
        games_valid = False
        issues.append(MatchIssue("games", "no_games", "Enter at least one game."))
    elif len(games) > MAX_GAMES:
        # One issue, not one per game of an oversized list.
        games_valid = False
        issues.append(
            MatchIssue("games", "too_many_games", f"Enter at most {MAX_GAMES} games.")
        )
    else:
        for index, game in enumerate(games):
            issue, score = _game_issue(index, game, target)
            if issue is not None:
                games_valid = False
                issues.append(issue)
            elif score is not None:
                scores.append(score)
    if target is None:
        # Without a valid target the games' outcome cannot be trusted.
        games_valid = False

    if games_valid and best_of_valid:
        winners = [Team.A if a > b else Team.B for a, b in scores]
        if chosen_best_of is None:
            chosen_best_of = infer_best_of(winners)
            if chosen_best_of is None:
                issues.append(MatchIssue("best_of", "cannot_infer", _CANNOT_INFER))
        else:
            deciding = _deciding_game(winners, chosen_best_of)
            if deciding is None:
                issues.append(
                    MatchIssue(
                        "games", "not_decided", "The games do not decide the match."
                    )
                )
            elif deciding < len(winners) - 1:
                after = deciding + 1
                issues.append(
                    MatchIssue(
                        f"games.{after}",
                        "game_after_decided",
                        f"Game {after + 1} was played after the match was decided.",
                    )
                )

    played_on_issue = _played_on_issue(played_on)
    if played_on_issue is not None:
        issues.append(played_on_issue)

    if (
        issues
        or match_format is None
        or players_a is None
        or players_b is None
        or scoring is None
        or target is None
        or chosen_best_of is None
    ):
        # Each None above always comes with an issue.
        raise MatchValidationError(issues)
    return ValidatedMatch(
        format=match_format,
        team_a=players_a,
        team_b=players_b,
        games=tuple(scores),
        played_on=played_on,
        best_of=chosen_best_of,
        game_target=target,
        scoring_type=scoring,
    )
