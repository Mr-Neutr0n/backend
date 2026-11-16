"""Who may create a Match, and who may change one (#79). Not built yet."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from django.contrib.auth.models import AnonymousUser

from apps.clubs.models import Club
from apps.events.models import Event
from apps.matches.models import Match

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

    from apps.partners.models import PartnerApplication

type Actor = _User | AnonymousUser | PartnerApplication


@dataclass(frozen=True)
class MatchSubmission:
    """What a permission check needs to know about a new Match."""

    event: Event | None
    club: Club | None
    player_ids: frozenset[int]


class MatchPermissionDenied(PermissionError):
    """The actor may not submit this match."""

    message: ClassVar[str] = "You are not allowed to submit this match."

    def __init__(self) -> None:
        super().__init__(self.message)


def can_create_match(actor: Actor, submission: MatchSubmission) -> bool:
    raise NotImplementedError


def can_change_match(actor: Actor, match: Match) -> bool:
    raise NotImplementedError


def check_can_create_match(actor: Actor, submission: MatchSubmission) -> None:
    raise NotImplementedError
