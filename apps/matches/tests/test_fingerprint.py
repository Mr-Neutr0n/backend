"""The match fingerprint: the same match in any team or player order hashes
alike, and any change to the players, date, or scores changes it.
"""

import re
from datetime import date

from apps.matches.services import (
    _external_id_lock_key,
    _lineup_lock_key,
    match_fingerprint,
)

PLAYED_ON = date(2026, 6, 1)
TEAM_A = (11, 12)
TEAM_B = (21, 22)
GAMES = ((11, 7), (9, 11), (11, 4))


def _swapped(games: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    return tuple((b, a) for a, b in games)


def test_fingerprint_is_a_sha256_hex_digest() -> None:
    fingerprint = match_fingerprint(TEAM_A, TEAM_B, PLAYED_ON, GAMES)

    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)


def test_same_inputs_give_the_same_fingerprint() -> None:
    assert match_fingerprint(TEAM_A, TEAM_B, PLAYED_ON, GAMES) == match_fingerprint(
        list(TEAM_A), list(TEAM_B), PLAYED_ON, [list(game) for game in GAMES]
    )


def test_swapping_teams_with_their_scores_keeps_the_fingerprint() -> None:
    assert match_fingerprint(TEAM_A, TEAM_B, PLAYED_ON, GAMES) == match_fingerprint(
        TEAM_B, TEAM_A, PLAYED_ON, _swapped(GAMES)
    )


def test_reordering_players_in_a_team_keeps_the_fingerprint() -> None:
    assert match_fingerprint(TEAM_A, TEAM_B, PLAYED_ON, GAMES) == match_fingerprint(
        TEAM_A[::-1], TEAM_B[::-1], PLAYED_ON, GAMES
    )


def test_swapping_teams_without_their_scores_changes_the_fingerprint() -> None:
    assert match_fingerprint(TEAM_A, TEAM_B, PLAYED_ON, GAMES) != match_fingerprint(
        TEAM_B, TEAM_A, PLAYED_ON, GAMES
    )


def test_a_different_player_changes_the_fingerprint() -> None:
    base = match_fingerprint(TEAM_A, TEAM_B, PLAYED_ON, GAMES)

    assert base != match_fingerprint((11, 13), TEAM_B, PLAYED_ON, GAMES)
    assert base != match_fingerprint(TEAM_A, (21, 23), PLAYED_ON, GAMES)


def test_moving_a_player_to_the_other_team_changes_the_fingerprint() -> None:
    assert match_fingerprint(TEAM_A, TEAM_B, PLAYED_ON, GAMES) != match_fingerprint(
        (11, 21), (12, 22), PLAYED_ON, GAMES
    )


def test_a_different_date_changes_the_fingerprint() -> None:
    assert match_fingerprint(TEAM_A, TEAM_B, PLAYED_ON, GAMES) != match_fingerprint(
        TEAM_A, TEAM_B, date(2026, 6, 2), GAMES
    )


def test_a_different_score_changes_the_fingerprint() -> None:
    changed = ((11, 7), (9, 11), (11, 5))

    assert match_fingerprint(TEAM_A, TEAM_B, PLAYED_ON, GAMES) != match_fingerprint(
        TEAM_A, TEAM_B, PLAYED_ON, changed
    )


def test_a_different_number_of_games_changes_the_fingerprint() -> None:
    assert match_fingerprint(TEAM_A, TEAM_B, PLAYED_ON, GAMES) != match_fingerprint(
        TEAM_A, TEAM_B, PLAYED_ON, GAMES[:2]
    )


def test_game_order_matters() -> None:
    assert match_fingerprint(TEAM_A, TEAM_B, PLAYED_ON, GAMES) != match_fingerprint(
        TEAM_A, TEAM_B, PLAYED_ON, (GAMES[1], GAMES[0], GAMES[2])
    )


def test_lineup_lock_key_ignores_team_and_player_order_and_scores() -> None:
    key = _lineup_lock_key(TEAM_A, TEAM_B, PLAYED_ON)

    assert key == _lineup_lock_key(TEAM_B, TEAM_A, PLAYED_ON)
    assert key == _lineup_lock_key(TEAM_A[::-1], TEAM_B[::-1], PLAYED_ON)
    assert -(2**63) <= key < 2**63


def test_lineup_lock_key_changes_with_players_or_date() -> None:
    key = _lineup_lock_key(TEAM_A, TEAM_B, PLAYED_ON)

    assert key != _lineup_lock_key((11, 13), TEAM_B, PLAYED_ON)
    assert key != _lineup_lock_key(TEAM_A, TEAM_B, date(2026, 6, 2))


def test_external_id_lock_key_depends_on_application_and_id() -> None:
    key = _external_id_lock_key(1, "ext-1")

    assert key == _external_id_lock_key(1, "ext-1")
    assert key != _external_id_lock_key(2, "ext-1")
    assert key != _external_id_lock_key(1, "ext-2")
    assert -(2**63) <= key < 2**63
