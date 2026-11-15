"""Matches, their participants, and their games: what the models refuse.

Each database rule is tested with a direct save that skips ``full_clean()``,
so the constraint itself is what refuses the row.
"""

import re
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.matches.models import (
    MAX_GAMES,
    MAX_UTC_OFFSET_MINUTES,
    MIN_UTC_OFFSET_MINUTES,
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
from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory
from apps.players.models import Player
from apps.players.tests.factories import PlayerFactory
from apps.public_ids.codes import CodeType
from apps.public_ids.models import IssuedCode

pytestmark = pytest.mark.django_db

MATCH_CODE = re.compile(r"^M-[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}$")

# A made-up value that must never show up in a validation message.
MARKER = "zqxjmarker"

PLAYED_ON = date(2026, 6, 1)
# 19:00 at the venue, seven hours behind UTC: 02:00 UTC the next day.
VENUE_OFFSET = -420
PLAYED_AT = datetime(2026, 6, 1, 19, 0, tzinfo=timezone(timedelta(minutes=-420)))


@pytest.fixture
def user() -> User:
    made: User = UserFactory.create()
    return made


@pytest.fixture
def application() -> PartnerApplication:
    made: PartnerApplication = PartnerApplicationFactory.create()
    return made


def _values(user: User | None, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "format": MatchFormat.SINGLES,
        "played_on": PLAYED_ON,
        "best_of": BestOf.ONE,
        "submitted_by_user": user,
    }
    values.update(overrides)
    return values


def _messages(error: ValidationError) -> str:
    return " ".join(
        message for messages in error.message_dict.values() for message in messages
    )


def _refused(constraint: str, **values: Any) -> None:
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Match.objects.create(**values)
    assert constraint in str(error.value)


def _clean_errors(**values: Any) -> ValidationError:
    match = Match(**values)
    with pytest.raises(ValidationError) as error:
        match.full_clean()
    return error.value


# Codes and str (criteria 4, 18).


def test_match_code_type_is_match() -> None:
    assert Match.public_code_type is CodeType.MATCH


def test_match_gets_a_match_code_issued_through_the_registry(user: User) -> None:
    match = Match.objects.create(**_values(user))

    assert MATCH_CODE.match(match.public_code)
    assert IssuedCode.objects.filter(code=match.public_code).exists()


def test_two_matches_get_distinct_codes(user: User) -> None:
    first = Match.objects.create(**_values(user))
    second = Match.objects.create(**_values(user))

    assert first.public_code != second.public_code


def test_str_is_the_open_code(user: User) -> None:
    match = Match.objects.create(**_values(user))

    assert str(match) == match.public_code


def test_valid_match_passes_full_clean(user: User) -> None:
    Match(**_values(user)).full_clean()


# Defaults (criteria 10, 11).


def test_match_saved_without_scoring_type_is_side_out(user: User) -> None:
    match = Match.objects.create(**_values(user))
    match.refresh_from_db()

    assert match.scoring_type == ScoringType.SIDE_OUT


def test_new_match_is_pending_with_target_11_and_sequence_0(user: User) -> None:
    match = Match.objects.create(**_values(user))
    match.refresh_from_db()

    assert match.status == MatchStatus.PENDING
    assert match.game_target == GameTarget.ELEVEN
    assert match.sequence == 0


def test_choice_values() -> None:
    # Equal to open_engine.ScoringType's values.
    assert set(ScoringType.values) == {"side_out", "rally"}
    # The two base values of open_engine.RatingFormat.
    assert set(MatchFormat.values) == {"singles", "doubles"}
    # MatchStatus, BestOf, and Team have no engine enum.
    assert set(MatchStatus.values) == {"pending", "confirmed", "disputed", "voided"}
    assert set(BestOf.values) == {1, 3, 5}
    # The points in the engine's ALL_GAME_FORMATS.
    assert set(GameTarget.values) == {11, 15, 21}
    assert set(Team.values) == {"A", "B"}
    assert MAX_GAMES == 5
    assert (MIN_UTC_OFFSET_MINUTES, MAX_UTC_OFFSET_MINUTES) == (-720, 840)


# Submitter (criterion 1).


def test_both_submitters_are_refused(
    user: User, application: PartnerApplication
) -> None:
    _refused(
        "matches_match_one_submitter",
        **_values(user, submitted_by_application=application),
    )


def test_no_submitter_is_refused() -> None:
    _refused("matches_match_one_submitter", **_values(None))


def test_application_submitter_alone_is_accepted(
    application: PartnerApplication,
) -> None:
    match = Match.objects.create(**_values(None, submitted_by_application=application))

    assert match.submitted_by_user is None


def test_full_clean_refuses_both_submitters(
    user: User, application: PartnerApplication
) -> None:
    error = _clean_errors(**_values(user, submitted_by_application=application))

    assert "submitted_by_user" in error.message_dict


def test_full_clean_refuses_no_submitter() -> None:
    error = _clean_errors(**_values(None))

    assert "submitted_by_user" in error.message_dict


# external_id (criteria 3, 14).


def test_external_id_is_unique_per_application(
    application: PartnerApplication,
) -> None:
    values = _values(None, submitted_by_application=application, external_id="x-1")
    Match.objects.create(**values)

    _refused("matches_match_external_id_unique_per_application", **values)


def test_same_external_id_on_two_applications_is_accepted(
    application: PartnerApplication,
) -> None:
    other: PartnerApplication = PartnerApplicationFactory.create()
    Match.objects.create(
        **_values(None, submitted_by_application=application, external_id="x-1")
    )

    Match.objects.create(
        **_values(None, submitted_by_application=other, external_id="x-1")
    )


def test_empty_external_id_repeats_on_one_application(
    application: PartnerApplication,
) -> None:
    values = _values(None, submitted_by_application=application)
    Match.objects.create(**values)
    Match.objects.create(**values)

    assert Match.objects.filter(submitted_by_application=application).count() == 2


def test_full_clean_refuses_a_duplicate_external_id_without_the_value(
    application: PartnerApplication,
) -> None:
    values = _values(None, submitted_by_application=application, external_id=MARKER)
    Match.objects.create(**values)

    error = _clean_errors(**values)

    assert MARKER not in _messages(error)


def test_external_id_on_an_account_submission_is_refused(user: User) -> None:
    _refused(
        "matches_match_external_id_needs_application",
        **_values(user, external_id="x-1"),
    )


def test_full_clean_refuses_external_id_on_an_account_submission(
    user: User,
) -> None:
    error = _clean_errors(**_values(user, external_id=MARKER))

    assert "external_id" in error.message_dict
    assert MARKER not in _messages(error)


# Sequence (criterion 6).


def test_negative_sequence_is_refused(user: User) -> None:
    _refused("matches_match_sequence_check", **_values(user, sequence=-1))


# Choices at the database (criteria 7, 8, 9, 11).


@pytest.mark.parametrize("best_of", [2, 7])
def test_best_of_outside_1_3_5_is_refused(user: User, best_of: int) -> None:
    _refused("matches_match_best_of_valid", **_values(user, best_of=best_of))


@pytest.mark.parametrize("best_of", [1, 3, 5])
def test_best_of_1_3_5_is_accepted(user: User, best_of: int) -> None:
    Match.objects.create(**_values(user, best_of=best_of))


@pytest.mark.parametrize("target", [9, 25])
def test_game_target_outside_11_15_21_is_refused(user: User, target: int) -> None:
    _refused("matches_match_game_target_valid", **_values(user, game_target=target))


@pytest.mark.parametrize("target", [11, 15, 21])
def test_game_target_11_15_21_is_accepted(user: User, target: int) -> None:
    Match.objects.create(**_values(user, game_target=target))


def test_bad_scoring_type_is_refused(user: User) -> None:
    _refused("matches_match_scoring_type_valid", **_values(user, scoring_type="tennis"))


def test_bad_status_is_refused(user: User) -> None:
    _refused("matches_match_status_valid", **_values(user, status="deleted"))


def test_bad_format_is_refused(user: User) -> None:
    _refused("matches_match_format_valid", **_values(user, format="triples"))


# played_at and its offset (criterion 13).


def test_played_at_with_offset_on_its_local_date_is_accepted(user: User) -> None:
    match = Match.objects.create(
        **_values(user, played_at=PLAYED_AT, played_at_utc_offset=VENUE_OFFSET)
    )
    match.refresh_from_db()

    assert match.played_at == PLAYED_AT
    local = match.played_at.astimezone(UTC) + timedelta(
        minutes=match.played_at_utc_offset or 0
    )
    assert local.date() == match.played_on


def test_played_at_on_the_utc_date_but_not_the_local_date_is_refused(
    user: User,
) -> None:
    _refused(
        "matches_match_played_at_local_date",
        **_values(
            user,
            played_on=date(2026, 6, 2),
            played_at=PLAYED_AT,
            played_at_utc_offset=VENUE_OFFSET,
        ),
    )


def test_played_at_at_plus_14_on_its_local_date_is_accepted(user: User) -> None:
    # 00:30 on 2026-06-01 at +14:00 is 10:30 UTC on 2026-05-31.
    played_at = datetime(2026, 5, 31, 10, 30, tzinfo=UTC)

    Match.objects.create(**_values(user, played_at=played_at, played_at_utc_offset=840))


def test_played_at_at_plus_14_on_the_utc_date_is_refused(user: User) -> None:
    played_at = datetime(2026, 5, 31, 10, 30, tzinfo=UTC)

    _refused(
        "matches_match_played_at_local_date",
        **_values(
            user,
            played_on=date(2026, 5, 31),
            played_at=played_at,
            played_at_utc_offset=840,
        ),
    )


def test_played_at_without_offset_is_refused(user: User) -> None:
    _refused("matches_match_played_at_pair", **_values(user, played_at=PLAYED_AT))


def test_offset_without_played_at_is_refused(user: User) -> None:
    _refused(
        "matches_match_played_at_pair",
        **_values(user, played_at_utc_offset=VENUE_OFFSET),
    )


@pytest.mark.parametrize("offset", [-721, 841])
def test_offset_out_of_range_is_refused(user: User, offset: int) -> None:
    played_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC) - timedelta(minutes=offset)

    _refused(
        "matches_match_played_at_utc_offset_range",
        **_values(user, played_at=played_at, played_at_utc_offset=offset),
    )


def test_full_clean_refuses_a_mismatched_local_date(user: User) -> None:
    error = _clean_errors(
        **_values(
            user,
            played_on=date(2026, 6, 2),
            played_at=PLAYED_AT,
            played_at_utc_offset=VENUE_OFFSET,
        )
    )

    assert "played_on" in error.message_dict


def test_full_clean_accepts_the_local_date(user: User) -> None:
    Match(
        **_values(user, played_at=PLAYED_AT, played_at_utc_offset=VENUE_OFFSET)
    ).full_clean()


def test_full_clean_refuses_played_at_without_offset(user: User) -> None:
    error = _clean_errors(**_values(user, played_at=PLAYED_AT))

    assert "played_at_utc_offset" in error.message_dict


def test_full_clean_refuses_offset_without_played_at(user: User) -> None:
    error = _clean_errors(**_values(user, played_at_utc_offset=VENUE_OFFSET))

    assert "played_at" in error.message_dict


@pytest.mark.parametrize("offset", [-721, 841])
def test_full_clean_refuses_offset_out_of_range(user: User, offset: int) -> None:
    error = _clean_errors(
        **_values(user, played_at=PLAYED_AT, played_at_utc_offset=offset)
    )

    assert "played_at_utc_offset" in error.message_dict


# Messages never echo the submitted value (criterion 17).


@pytest.mark.parametrize(
    "field",
    [
        "format",
        "status",
        "scoring_type",
        "best_of",
        "game_target",
        "sequence",
        "played_on",
        "played_at",
        "played_at_utc_offset",
    ],
)
def test_bad_value_message_does_not_echo_it(user: User, field: str) -> None:
    error = _clean_errors(**_values(user, **{field: MARKER}))

    assert field in error.message_dict
    assert MARKER not in _messages(error)


@pytest.mark.parametrize("field", ["best_of", "game_target"])
def test_bad_integer_choice_message_does_not_echo_it(user: User, field: str) -> None:
    error = _clean_errors(**_values(user, **{field: 987654}))

    assert field in error.message_dict
    assert "987654" not in _messages(error)


@pytest.mark.parametrize(
    "field",
    ["event_id", "club_id", "submitted_by_user_id", "submitted_by_application_id"],
)
def test_missing_link_message_does_not_echo_the_id(field: str) -> None:
    values = _values(None, **{field: 987654321})
    error = _clean_errors(**values)

    assert "987654321" not in _messages(error)


# Participants (criterion 12).


@pytest.fixture
def match(user: User) -> Match:
    made: Match = Match.objects.create(**_values(user))
    return made


@pytest.fixture
def player() -> Player:
    made: Player = PlayerFactory.create()
    return made


def test_participant_on_team_a_or_b_is_accepted(match: Match, player: Player) -> None:
    participant = MatchParticipant.objects.create(
        match=match, player=player, team=Team.A
    )

    assert list(match.participants.all()) == [participant]


def test_participant_team_other_than_a_or_b_is_refused(
    match: Match, player: Player
) -> None:
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        MatchParticipant.objects.create(match=match, player=player, team="C")
    assert "matches_matchparticipant_team_valid" in str(error.value)


def test_same_player_twice_in_one_match_is_refused(
    match: Match, player: Player
) -> None:
    MatchParticipant.objects.create(match=match, player=player, team=Team.A)

    with pytest.raises(IntegrityError) as error, transaction.atomic():
        MatchParticipant.objects.create(match=match, player=player, team=Team.B)
    assert "matches_matchparticipant_player_once_per_match" in str(error.value)


def test_participant_str_is_the_match_code_and_team(
    match: Match, player: Player
) -> None:
    participant = MatchParticipant.objects.create(
        match=match, player=player, team=Team.A
    )

    assert str(participant) == f"{match.public_code} team A"
    assert player.display_name not in str(participant)


def test_participant_team_message_does_not_echo_it(
    match: Match, player: Player
) -> None:
    participant = MatchParticipant(match=match, player=player, team=MARKER)

    with pytest.raises(ValidationError) as error:
        participant.full_clean()

    assert "team" in error.value.message_dict
    assert MARKER not in _messages(error.value)


# Games (criteria 5, 15).


def _game(match: Match, **overrides: Any) -> Game:
    values: dict[str, Any] = {
        "match": match,
        "game_number": 1,
        "team_a_score": 11,
        "team_b_score": 7,
    }
    values.update(overrides)
    game: Game = Game.objects.create(**values)
    return game


def _game_refused(constraint: str, match: Match, **overrides: Any) -> None:
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        _game(match, **overrides)
    assert constraint in str(error.value)


def test_five_games_are_accepted(match: Match) -> None:
    for number in range(1, MAX_GAMES + 1):
        _game(match, game_number=number)

    assert [game.game_number for game in match.games.all()] == [1, 2, 3, 4, 5]


def test_sixth_game_is_refused(match: Match) -> None:
    for number in range(1, MAX_GAMES + 1):
        _game(match, game_number=number)

    _game_refused("matches_game_number_range", match, game_number=6)


def test_game_number_0_is_refused(match: Match) -> None:
    _game_refused("matches_game_number_range", match, game_number=0)


def test_two_games_with_one_number_are_refused(match: Match) -> None:
    _game(match, game_number=1)

    _game_refused("matches_game_number_once_per_match", match, game_number=1)


@pytest.mark.parametrize("side", ["team_a_score", "team_b_score"])
def test_negative_score_is_refused(match: Match, side: str) -> None:
    _game_refused(f"matches_game_{side}_check", match, **{side: -1})


def test_game_str_is_the_match_code_and_number(match: Match) -> None:
    game = _game(match, game_number=2)

    assert str(game) == f"{match.public_code} game 2"
