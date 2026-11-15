"""Verifying and unverifying an Organizer: who may, and what is recorded."""

from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.models import AnonymousUser, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditAction, AuditEvent
from apps.audit.services import snapshot
from apps.clubs.models import MemberRole, Organizer, OrganizerMember
from apps.clubs.services import (
    NotAllowedToVerify,
    unverify_organizer,
    verify_organizer,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

pytestmark = pytest.mark.django_db

FIELDS = ["verified_at", "verified_by"]
REASON = "Made-up reason: checked the organizer's documents."


def _verifier(**fields: object) -> "_User":
    account: _User = UserFactory.create(is_staff=True, **fields)
    account.user_permissions.add(
        Permission.objects.get(content_type__app_label="clubs", codename="verify_organizer")
    )
    # Drop the cached permissions, so has_perm reads the new grant.
    return type(account)._default_manager.get(pk=account.pk)


def _events() -> list[AuditEvent]:
    return list(
        AuditEvent.objects.filter(
            target_content_type=ContentType.objects.get_for_model(Organizer)
        ).order_by("pk")
    )


def _verified(by: "_User") -> Organizer:
    organizer = Organizer.objects.create(name="Made-up Events")
    Organizer.objects.filter(pk=organizer.pk).update(
        verified_at=timezone.now(), verified_by=by
    )
    organizer.refresh_from_db()
    return organizer


@pytest.fixture
def organizer() -> Organizer:
    return Organizer.objects.create(name="Made-up Events")


def test_verify_sets_fields_and_records_one_event(organizer: Organizer) -> None:
    actor = _verifier()
    before = timezone.now()

    result = verify_organizer(organizer, actor=actor, reason=REASON)

    assert result is organizer
    assert organizer.is_verified is True
    assert organizer.verified_by == actor
    assert organizer.verified_at is not None
    assert before <= organizer.verified_at <= timezone.now()
    stored = Organizer.objects.get(pk=organizer.pk)
    assert stored.verified_at == organizer.verified_at
    assert stored.verified_by_id == actor.pk
    [event] = _events()
    assert event.action == AuditAction.ORGANIZER_VERIFY
    assert event.actor_user_id == actor.pk
    assert event.target_object_id == str(organizer.pk)
    assert event.before == {"verified_at": None, "verified_by": None}
    # As the audit log stores it (to the millisecond).
    assert event.after == snapshot(stored, FIELDS)
    assert event.after["verified_by"] == actor.pk
    assert event.reason == REASON


def test_superuser_can_verify(organizer: Organizer) -> None:
    actor = UserFactory.create(is_staff=True, is_superuser=True)

    verify_organizer(organizer, actor=actor)

    assert organizer.is_verified is True
    assert len(_events()) == 1


def test_unverify_clears_fields_and_records_one_event() -> None:
    actor = _verifier()
    organizer = _verified(by=actor)
    stored_before = snapshot(organizer, FIELDS)

    unverify_organizer(organizer, actor=actor, reason=REASON)

    assert organizer.is_verified is False
    assert organizer.verified_by is None
    stored = Organizer.objects.get(pk=organizer.pk)
    assert (stored.verified_at, stored.verified_by_id) == (None, None)
    [event] = _events()
    assert event.action == AuditAction.ORGANIZER_UNVERIFY
    assert event.actor_user_id == actor.pk
    assert event.before == stored_before
    assert event.before["verified_by"] == actor.pk
    assert event.before["verified_at"] is not None
    assert event.after == {"verified_at": None, "verified_by": None}
    assert event.reason == REASON


def _anonymous() -> AnonymousUser:
    return AnonymousUser()


def _inactive_with_perm() -> "_User":
    return _verifier(is_active=False)


def _staff_without_perm() -> "_User":
    return UserFactory.create(is_staff=True)


def _inactive_superuser() -> "_User":
    return UserFactory.create(is_staff=True, is_superuser=True, is_active=False)


REFUSED_ACTORS: list[Callable[[], "_User | AnonymousUser"]] = [
    _anonymous,
    _inactive_with_perm,
    _staff_without_perm,
    _inactive_superuser,
]


@pytest.mark.parametrize("make_actor", REFUSED_ACTORS)
def test_verify_refuses_actor_without_permission(
    organizer: Organizer, make_actor: Callable[[], "_User | AnonymousUser"]
) -> None:
    actor = make_actor()

    with pytest.raises(NotAllowedToVerify):
        verify_organizer(organizer, actor=actor)  # type: ignore[arg-type]

    stored = Organizer.objects.get(pk=organizer.pk)
    assert (stored.verified_at, stored.verified_by_id) == (None, None)
    assert organizer.is_verified is False
    assert _events() == []


@pytest.mark.parametrize("make_actor", REFUSED_ACTORS)
def test_unverify_refuses_actor_without_permission(
    make_actor: Callable[[], "_User | AnonymousUser"],
) -> None:
    organizer = _verified(by=UserFactory.create(is_staff=True))
    actor = make_actor()

    with pytest.raises(NotAllowedToVerify):
        unverify_organizer(organizer, actor=actor)  # type: ignore[arg-type]

    assert Organizer.objects.get(pk=organizer.pk).is_verified is True
    assert organizer.is_verified is True
    assert _events() == []


@pytest.mark.parametrize("role", MemberRole.values)
@pytest.mark.parametrize("superuser", [False, True])
def test_member_cannot_verify_own_organizer(
    organizer: Organizer, role: str, superuser: bool
) -> None:
    actor = (
        UserFactory.create(is_staff=True, is_superuser=True)
        if superuser
        else _verifier()
    )
    OrganizerMember.objects.create(organizer=organizer, account=actor, role=role)

    with pytest.raises(NotAllowedToVerify):
        verify_organizer(organizer, actor=actor)

    stored = Organizer.objects.get(pk=organizer.pk)
    assert stored.is_verified is False
    assert organizer.is_verified is False
    assert _events() == []


def test_member_cannot_unverify_own_organizer() -> None:
    organizer = _verified(by=UserFactory.create(is_staff=True))
    actor = _verifier()
    OrganizerMember.objects.create(
        organizer=organizer, account=actor, role=MemberRole.ADMIN
    )

    with pytest.raises(NotAllowedToVerify):
        unverify_organizer(organizer, actor=actor)

    assert Organizer.objects.get(pk=organizer.pk).is_verified is True
    assert _events() == []


def test_member_of_another_organizer_can_verify(organizer: Organizer) -> None:
    actor = _verifier()
    other = Organizer.objects.create(name="Made-up Other Events")
    OrganizerMember.objects.create(organizer=other, account=actor, role="admin")

    verify_organizer(organizer, actor=actor)

    assert organizer.is_verified is True


def test_verifying_twice_records_one_event(organizer: Organizer) -> None:
    first = _verifier()
    second = _verifier()
    verify_organizer(organizer, actor=first)
    verified_at = organizer.verified_at

    verify_organizer(organizer, actor=second)

    stored = Organizer.objects.get(pk=organizer.pk)
    assert stored.verified_at == verified_at
    assert stored.verified_by_id == first.pk
    assert len(_events()) == 1


def test_verifying_with_a_stale_instance_records_one_event(
    organizer: Organizer,
) -> None:
    stale = Organizer.objects.get(pk=organizer.pk)
    actor = _verifier()
    verify_organizer(organizer, actor=actor)

    verify_organizer(stale, actor=_verifier())

    assert len(_events()) == 1
    # The stale instance now shows the stored state.
    assert stale.verified_at == organizer.verified_at
    assert stale.verified_by == actor


def test_unverifying_an_unverified_organizer_records_nothing(
    organizer: Organizer,
) -> None:
    unverify_organizer(organizer, actor=_verifier())

    assert organizer.is_verified is False
    assert _events() == []


def test_verify_then_unverify_records_two_events(organizer: Organizer) -> None:
    actor = _verifier()

    verify_organizer(organizer, actor=actor)
    unverify_organizer(organizer, actor=actor)

    assert [event.action for event in _events()] == [
        AuditAction.ORGANIZER_VERIFY,
        AuditAction.ORGANIZER_UNVERIFY,
    ]


def test_unsaved_organizer_is_refused() -> None:
    with pytest.raises(Organizer.DoesNotExist):
        verify_organizer(Organizer(name="Made-up Events"), actor=_verifier())

    assert _events() == []
