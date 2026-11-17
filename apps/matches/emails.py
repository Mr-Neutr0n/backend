"""The match confirmation request email (issue #36).

It renders only: #37 decides when to send it and queues it with
``apps.emails.services.queue_email``.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from apps.emails.rendering import render_email
from apps.matches.models import Match, MatchStatus, Team
from apps.players.models import Player

TEMPLATE_PREFIX = "matches/email/confirmation_request"


@dataclass(frozen=True)
class PendingMatchLine:
    """One Match as the email lists it. No player is named."""

    code: str
    played_on: date
    scores: str
    url: str


def match_url(match: Match) -> str:
    """The web app's page for a Match, where a player confirms or disputes it.

    The ``/matches/{code}`` route is a new web app route; #37 and the web
    app adopt it.
    """
    return f"{settings.FRONTEND_URL}/matches/{match.public_code}"


def _line(player: Player, match: Match) -> PendingMatchLine:
    team = (
        match.participants.filter(player=player).values_list("team", flat=True).first()
    )
    if team is None:
        raise ValueError("The player did not play in every match.")
    if match.status != MatchStatus.PENDING:
        raise ValueError("A confirmation request is only for pending matches.")
    scores = []
    for game in match.games.order_by("game_number"):
        mine, theirs = game.team_a_score, game.team_b_score
        if team == Team.B:
            mine, theirs = theirs, mine
        scores.append(f"{mine}-{theirs}")
    if not scores:
        raise ValueError("A confirmation request needs a match with games.")
    return PendingMatchLine(
        code=str(match.public_code),
        played_on=match.played_on,
        scores=", ".join(scores),
        url=match_url(match),
    )


def render_confirmation_request(
    player: Player, matches: Sequence[Match]
) -> EmailMultiAlternatives:
    """Ask a Player to confirm one or more Matches they played in.

    Each Match is listed in the order given, with its OPEN Code, the date
    it was played, the game scores from the Player's side (their team
    first), and a link to it in the web app (``match_url``). The email
    names no player, location, or submitter, so no other player's details
    reach the mailbox or the provider's logs.

    Refuses, with fixed text that names no address or code: a Player
    whose Account is inactive, an empty list, the same Match more than
    once, a Match the Player did not play in, a Match that is not
    pending, and a Match with no games.
    """
    if not player.account.is_active:
        raise ValueError("A confirmation request needs an active account.")
    if not matches:
        raise ValueError("A confirmation request needs at least one match.")
    if len({match.pk for match in matches}) != len(matches):
        raise ValueError("A confirmation request lists each match once.")
    lines = [_line(player, match) for match in matches]
    return render_email(TEMPLATE_PREFIX, player.account.email, {"matches": lines})
