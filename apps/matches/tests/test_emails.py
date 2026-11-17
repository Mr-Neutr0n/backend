"""The match confirmation request email (issue #36).

One email to one Player lists one or more pending Matches they played
in, with each Match's OPEN Code, date, scores from the Player's side, and
a link to it in the web app. It names no other player. Made-up data only.
"""

from datetime import date

import pytest
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from apps.emails.services import queue_email
from apps.emails.tests.hygiene import assert_clean_message
from apps.matches.emails import render_confirmation_request
from apps.matches.models import Game, Match, MatchFormat, MatchParticipant, Team
from apps.matches.tests.factories import MatchFactory
from apps.players.models import Player
from apps.players.tests.factories import PlayerFactory

pytestmark = pytest.mark.django_db

FRONTEND_URL: str = settings.FRONTEND_URL
REASON = (
    "You received this email because you played in a match that was "
    "submitted to OPEN and is waiting for your confirmation."
)
AUTOMATED = (
    "This is an automated message from OPEN, the Open Pickleball Evaluation Network."
)


def _match(
    team_a: list[Player],
    team_b: list[Player],
    scores: list[tuple[int, int]],
    played_on: date = date(2026, 5, 3),
) -> Match:
    """A pending Match with these players and game scores, in this order."""
    match_format = MatchFormat.DOUBLES if len(team_a) == 2 else MatchFormat.SINGLES
    best_of = 1 if len(scores) == 1 else 3
    match = MatchFactory.create(
        format=match_format,
        best_of=best_of,
        played_on=played_on,
        participants=False,
        games=False,
    )
    for team, players in ((Team.A, team_a), (Team.B, team_b)):
        for player in players:
            MatchParticipant.objects.create(match=match, player=player, team=team)
    # Inserted out of order: the email lists them by game number.
    for number, (a, b) in reversed(list(enumerate(scores, start=1))):
        Game.objects.create(
            match=match, game_number=number, team_a_score=a, team_b_score=b
        )
    return match


def _html(message: EmailMultiAlternatives) -> str:
    [(html, mimetype)] = message.alternatives
    assert mimetype == "text/html"
    return str(html)


def _link(match: Match) -> str:
    return f"{FRONTEND_URL}/matches/{match.public_code}"


def test_one_match() -> None:
    me, them = PlayerFactory.create(), PlayerFactory.create()
    match = _match([me], [them], [(11, 7)])

    message = render_confirmation_request(me, [match])

    assert message.to == [me.account.email]
    assert message.subject == "A match is waiting for your confirmation on OPEN"
    assert message.body.splitlines()[0] == "OPEN"
    assert str(match.public_code) in message.body
    assert "May 3, 2026" in message.body
    assert "11-7" in message.body
    assert _link(match) in message.body
    html = _html(message)
    assert f'href="{_link(match)}"' in html
    assert "11-7" in html


def test_scores_are_from_the_recipients_side() -> None:
    a, b = PlayerFactory.create(), PlayerFactory.create()
    match = _match([a], [b], [(11, 7), (9, 11), (11, 5)])

    for_a = render_confirmation_request(a, [match])
    for_b = render_confirmation_request(b, [match])

    assert "11-7, 9-11, 11-5" in for_a.body
    assert "11-7, 9-11, 11-5" in _html(for_a)
    assert "7-11, 11-9, 5-11" in for_b.body
    assert "7-11, 11-9, 5-11" in _html(for_b)


def test_several_matches_in_the_order_given() -> None:
    me = PlayerFactory.create()
    first = _match([me], [PlayerFactory.create()], [(11, 3)], date(2026, 4, 1))
    second = _match([PlayerFactory.create()], [me], [(11, 9)], date(2026, 3, 1))

    message = render_confirmation_request(me, [first, second])

    assert message.subject == "Matches waiting for your confirmation on OPEN"
    for body in (message.body, _html(message)):
        assert body.index(str(first.public_code)) < body.index(str(second.public_code))
        assert "11-3" in body
        assert "9-11" in body
    assert _link(first) in message.body
    assert _link(second) in message.body


def test_no_player_is_named() -> None:
    players = [
        PlayerFactory.create(display_name=f"Zephyrine Made-up {letter}.")
        for letter in "QRST"
    ]
    me = players[0]
    match = _match(players[:2], players[2:], [(11, 7)])

    message = render_confirmation_request(me, [match])

    for body in (str(message.subject), message.body, _html(message)):
        for player in players:
            assert player.display_name not in body
            assert player.account.email not in body


def test_says_why_and_what_to_do() -> None:
    me = PlayerFactory.create()
    match = _match([me], [PlayerFactory.create()], [(11, 7)])

    message = render_confirmation_request(me, [match])

    for body in (message.body, _html(message)):
        assert REASON in body
        assert AUTOMATED in body
        assert "counts only once" in body
        assert "dispute" in body


def test_message_is_clean_and_queueable() -> None:
    me = PlayerFactory.create()
    match = _match([me], [PlayerFactory.create()], [(11, 7)])
    message = render_confirmation_request(me, [match])

    assert_clean_message(message)
    row = queue_email(message, template="matches/email/confirmation_request")
    assert row.html


def test_refuses_no_matches() -> None:
    with pytest.raises(ValueError, match="at least one match"):
        render_confirmation_request(PlayerFactory.create(), [])


def test_refuses_a_match_the_player_did_not_play() -> None:
    me = PlayerFactory.create()
    mine = _match([me], [PlayerFactory.create()], [(11, 7)])
    other = MatchFactory.create()

    with pytest.raises(ValueError, match="did not play") as caught:
        render_confirmation_request(me, [mine, other])

    text = str(caught.value)
    assert text == "The player did not play in every match."
    assert str(other.public_code) not in text
