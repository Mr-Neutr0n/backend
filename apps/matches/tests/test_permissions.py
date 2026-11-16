"""Who may create a Match, and who may change one (#79).

Table-driven: every actor kind against every match shape (event only,
club only, event and club, neither), for both functions. Made-up data only.
"""

import dataclasses
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
from django.contrib.auth.models import AnonymousUser

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Club, MemberRole, Organizer
from apps.clubs.services import unverify_organizer
from apps.clubs.tests.factories import (
    ClubFactory,
    ClubRoleFactory,
    OrganizerFactory,
    OrganizerMemberFactory,
    verified_organizer,
)
from apps.events.models import Event
from apps.events.tests.factories import EventFactory
from apps.matches.models import Match
from apps.matches.permissions import (
    Actor,
    MatchPermissionDenied,
    MatchSubmission,
    can_change_match,
    can_create_match,
    check_can_create_match,
)
from apps.matches.tests.factories import MatchFactory
from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import (
    ClubApplicationGrantFactory,
    PartnerApplicationFactory,
    approved_application,
)
from apps.players.models import Player
from apps.players.tests.factories import PlayerFactory

pytestmark = pytest.mark.django_db

EVENT = "event"
CLUB = "club"
EVENT_CLUB = "event_club"
NEITHER = "neither"
SHAPES = (EVENT, CLUB, EVENT_CLUB, NEITHER)


@dataclass
class Scene:
    """A verified Organizer's Event, a Club, and two Players."""

    organizer: Organizer
    event: Event
    club: Club
    players: list[Player] = field(default_factory=list)

    def submission(self, shape: str) -> MatchSubmission:
        return MatchSubmission(
            event=self.event if shape in (EVENT, EVENT_CLUB) else None,
            club=self.club if shape in (CLUB, EVENT_CLUB) else None,
            player_ids=frozenset(player.pk for player in self.players),
        )

    def match(self, shape: str, **kwargs: object) -> Match:
        made: Match = MatchFactory.create(
            event=self.event if shape in (EVENT, EVENT_CLUB) else None,
            club=self.club if shape in (CLUB, EVENT_CLUB) else None,
            games=False,
            participants=False,
            **kwargs,
        )
        return made


@pytest.fixture
def scene() -> Scene:
    organizer = verified_organizer()
    return Scene(
        organizer=organizer,
        event=EventFactory.create(organizer=organizer),
        club=ClubFactory.create(),
        players=[PlayerFactory.create(), PlayerFactory.create()],
    )


def _account() -> User:
    made: User = UserFactory.create()
    return made


def _member(scene: Scene, role: str = MemberRole.MATCH_MANAGER) -> User:
    account = _account()
    OrganizerMemberFactory.create(organizer=scene.organizer, account=account, role=role)
    return account


def _club_role(scene: Scene, role: str = MemberRole.MATCH_MANAGER) -> User:
    account = _account()
    ClubRoleFactory.create(club=scene.club, account=account, role=role)
    return account


def _every_role(scene: Scene) -> User:
    """An Account that is an Organizer admin, a Club admin, and plays."""
    account = scene.players[0].account
    OrganizerMemberFactory.create(
        organizer=scene.organizer, account=account, role=MemberRole.ADMIN
    )
    ClubRoleFactory.create(club=scene.club, account=account, role=MemberRole.ADMIN)
    return account


def _inactive(account: User) -> User:
    account.is_active = False
    account.save(update_fields=["is_active"])
    return account


def _application(
    scene: Scene, *, owned: bool, granted: bool, approved: bool = True
) -> PartnerApplication:
    owner = scene.organizer if owned else None
    application: PartnerApplication = (
        approved_application(organizer=owner)
        if approved
        else PartnerApplicationFactory.create(organizer=owner)
    )
    if granted:
        ClubApplicationGrantFactory.create(club=scene.club, application=application)
    return application


ActorBuilder = Callable[[Scene], Actor]

# Each actor kind and the shapes it may create a match for.
CREATE_TABLE: dict[str, tuple[ActorBuilder, frozenset[str]]] = {
    "organizer_admin": (
        lambda s: _member(s, MemberRole.ADMIN),
        frozenset({EVENT}),
    ),
    "organizer_match_manager": (
        lambda s: _member(s, MemberRole.MATCH_MANAGER),
        frozenset({EVENT}),
    ),
    "club_admin": (lambda s: _club_role(s, MemberRole.ADMIN), frozenset({CLUB})),
    "club_match_manager": (
        lambda s: _club_role(s, MemberRole.MATCH_MANAGER),
        frozenset({CLUB}),
    ),
    "organizer_member_with_club_role": (
        lambda s: _with_club_role(s, _member(s)),
        frozenset({EVENT, CLUB, EVENT_CLUB}),
    ),
    "participant": (lambda s: s.players[0].account, frozenset({NEITHER})),
    "unrelated_account": (lambda s: _account(), frozenset()),
    "every_role_and_plays": (_every_role, frozenset(SHAPES)),
    "inactive_every_role_and_plays": (
        lambda s: _inactive(_every_role(s)),
        frozenset(),
    ),
    "anonymous": (lambda s: AnonymousUser(), frozenset()),
    "application_owned": (
        lambda s: _application(s, owned=True, granted=False),
        frozenset({EVENT}),
    ),
    "application_granted": (
        lambda s: _application(s, owned=False, granted=True),
        frozenset({CLUB}),
    ),
    "application_owned_and_granted": (
        lambda s: _application(s, owned=True, granted=True),
        frozenset({EVENT, CLUB, EVENT_CLUB}),
    ),
    "unapproved_application_owned_and_granted": (
        lambda s: _application(s, owned=True, granted=True, approved=False),
        frozenset(),
    ),
    "unrelated_application": (
        lambda s: _application(s, owned=False, granted=False),
        frozenset(),
    ),
}


def _with_club_role(scene: Scene, account: User) -> User:
    ClubRoleFactory.create(club=scene.club, account=account)
    return account


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("kind", sorted(CREATE_TABLE))
def test_can_create_match(scene: Scene, kind: str, shape: str) -> None:
    build, permitted = CREATE_TABLE[kind]
    actor = build(scene)

    assert can_create_match(actor, scene.submission(shape)) is (shape in permitted)


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("kind", sorted(CREATE_TABLE))
def test_check_can_create_match_raises_only_when_refused(
    scene: Scene, kind: str, shape: str
) -> None:
    build, permitted = CREATE_TABLE[kind]
    actor = build(scene)
    submission = scene.submission(shape)

    if shape in permitted:
        check_can_create_match(actor, submission)
    else:
        with pytest.raises(MatchPermissionDenied) as error:
            check_can_create_match(actor, submission)
        assert str(error.value) == MatchPermissionDenied.message


# AC 1: an unverified Organizer's members and applications are refused.


@pytest.fixture
def unverified_scene() -> Scene:
    organizer = OrganizerFactory.create()
    return Scene(
        organizer=organizer,
        event=EventFactory.create(organizer=organizer),
        club=ClubFactory.create(),
        players=[PlayerFactory.create(), PlayerFactory.create()],
    )


UNVERIFIED_ACTORS: dict[str, ActorBuilder] = {
    "organizer_admin": lambda s: _member(s, MemberRole.ADMIN),
    "organizer_match_manager": lambda s: _member(s, MemberRole.MATCH_MANAGER),
    "organizer_member_with_club_role": lambda s: _with_club_role(s, _member(s)),
    "every_role_and_plays": _every_role,
    "application_owned": lambda s: _application(s, owned=True, granted=False),
    "application_owned_and_granted": (
        lambda s: _application(s, owned=True, granted=True)
    ),
}


@pytest.mark.parametrize("shape", [EVENT, EVENT_CLUB])
@pytest.mark.parametrize("kind", sorted(UNVERIFIED_ACTORS))
def test_unverified_organizer_cannot_create_for_its_event(
    unverified_scene: Scene, kind: str, shape: str
) -> None:
    actor = UNVERIFIED_ACTORS[kind](unverified_scene)

    assert not can_create_match(actor, unverified_scene.submission(shape))


def test_verification_is_read_from_the_database(scene: Scene) -> None:
    account = _member(scene, MemberRole.ADMIN)
    # The in-memory Event still holds the verified Organizer.
    stale_event = Event.objects.select_related("organizer").get(pk=scene.event.pk)
    assert stale_event.organizer.is_verified
    verifier = scene.organizer.verified_by
    assert verifier is not None
    unverify_organizer(scene.organizer, actor=verifier)
    submission = MatchSubmission(
        event=stale_event,
        club=None,
        player_ids=frozenset(p.pk for p in scene.players),
    )

    assert not can_create_match(account, submission)


def test_an_account_without_a_player_is_refused_self_submission(
    scene: Scene,
) -> None:
    assert not can_create_match(_account(), scene.submission(NEITHER))


def test_an_unexpected_actor_type_is_refused(scene: Scene) -> None:
    for shape in SHAPES:
        assert not can_create_match(object(), scene.submission(shape))  # type: ignore[arg-type]


# can_change_match.

# Each Account kind and the shapes of match it may change.
CHANGE_TABLE: dict[str, tuple[ActorBuilder, frozenset[str]]] = {
    "organizer_admin": (
        lambda s: _member(s, MemberRole.ADMIN),
        frozenset({EVENT, EVENT_CLUB}),
    ),
    "organizer_match_manager": (
        lambda s: _member(s, MemberRole.MATCH_MANAGER),
        frozenset({EVENT, EVENT_CLUB}),
    ),
    "club_admin": (
        lambda s: _club_role(s, MemberRole.ADMIN),
        frozenset({CLUB, EVENT_CLUB}),
    ),
    "club_match_manager": (
        lambda s: _club_role(s, MemberRole.MATCH_MANAGER),
        frozenset(),
    ),
    "participant": (lambda s: s.players[0].account, frozenset()),
    "unrelated_account": (lambda s: _account(), frozenset()),
    "every_role_and_plays": (_every_role, frozenset({EVENT, CLUB, EVENT_CLUB})),
    "inactive_every_role_and_plays": (
        lambda s: _inactive(_every_role(s)),
        frozenset(),
    ),
    "anonymous": (lambda s: AnonymousUser(), frozenset()),
    "application_owned_and_granted": (
        lambda s: _application(s, owned=True, granted=True),
        frozenset(),
    ),
}


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("kind", sorted(CHANGE_TABLE))
def test_can_change_match(scene: Scene, kind: str, shape: str) -> None:
    build, permitted = CHANGE_TABLE[kind]
    actor = build(scene)
    match = scene.match(shape)

    assert can_change_match(actor, match) is (shape in permitted)


@pytest.mark.parametrize("shape", SHAPES)
def test_the_submitting_account_cannot_change_its_own_match(
    scene: Scene, shape: str
) -> None:
    account = scene.players[0].account
    match = scene.match(shape, submitted_by_user=account)

    assert not can_change_match(account, match)


@pytest.mark.parametrize("shape", [EVENT, EVENT_CLUB])
def test_unverified_organizer_member_cannot_change(
    unverified_scene: Scene, shape: str
) -> None:
    account = _member(unverified_scene, MemberRole.ADMIN)

    assert not can_change_match(account, unverified_scene.match(shape))


# AC 3: only the submitting application, while approved, changes a match.


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("approved", [True, False])
def test_submitting_application_changes_its_match_only_while_approved(
    scene: Scene, shape: str, approved: bool
) -> None:
    application = _application(scene, owned=True, granted=True, approved=approved)
    match = scene.match(
        shape, submitted_by_user=None, submitted_by_application=application
    )

    assert can_change_match(application, match) is approved


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("owned", [True, False])
@pytest.mark.parametrize("granted", [True, False])
@pytest.mark.parametrize("approved", [True, False])
@pytest.mark.parametrize("submitted_by_application", [True, False])
def test_an_application_never_changes_a_match_it_did_not_submit(
    scene: Scene,
    shape: str,
    owned: bool,
    granted: bool,
    approved: bool,
    submitted_by_application: bool,
) -> None:
    other = _application(scene, owned=True, granted=True)
    if submitted_by_application:
        match = scene.match(
            shape, submitted_by_user=None, submitted_by_application=other
        )
    else:
        match = scene.match(shape)
    application = _application(scene, owned=owned, granted=granted, approved=approved)

    assert not can_change_match(application, match)


def test_an_unexpected_actor_type_cannot_change(scene: Scene) -> None:
    for shape in SHAPES:
        assert not can_change_match(object(), scene.match(shape))  # type: ignore[arg-type]


# AC 4: no rule reads payment status or entitlements.


def test_functions_take_only_the_actor_and_the_match() -> None:
    assert list(inspect.signature(can_create_match).parameters) == [
        "actor",
        "submission",
    ]
    assert list(inspect.signature(check_can_create_match).parameters) == [
        "actor",
        "submission",
    ]
    assert list(inspect.signature(can_change_match).parameters) == ["actor", "match"]


def test_submission_holds_only_event_club_and_players() -> None:
    names = [f.name for f in dataclasses.fields(MatchSubmission)]

    assert names == ["event", "club", "player_ids"]


def test_permission_denied_has_fixed_text() -> None:
    assert MatchPermissionDenied().message == MatchPermissionDenied.message
    assert str(MatchPermissionDenied()) == "You are not allowed to submit this match."
