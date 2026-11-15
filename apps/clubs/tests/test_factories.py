"""The clubs factories make valid records with made-up data."""

import pytest

from apps.clubs.models import Club, ClubRole, MemberRole, Organizer, OrganizerMember
from apps.clubs.tests.factories import (
    ClubFactory,
    ClubRoleFactory,
    OrganizerFactory,
    OrganizerMemberFactory,
)

pytestmark = pytest.mark.django_db


def test_club_is_valid_and_saved() -> None:
    club = ClubFactory.create()

    stored = Club.objects.get(pk=club.pk)
    stored.full_clean()
    assert stored.public_code.startswith("C-")
    assert stored.name


def test_organizer_is_valid_saved_and_unverified() -> None:
    organizer = OrganizerFactory.create()

    stored = Organizer.objects.get(pk=organizer.pk)
    stored.full_clean()
    assert stored.public_code.startswith("G-")
    assert stored.is_verified is False


def test_organizer_member_is_valid() -> None:
    member = OrganizerMemberFactory.create()

    stored = OrganizerMember.objects.get(pk=member.pk)
    stored.full_clean()
    assert stored.role == MemberRole.MATCH_MANAGER


def test_club_role_is_valid() -> None:
    role = ClubRoleFactory.create()

    stored = ClubRole.objects.get(pk=role.pk)
    stored.full_clean()
    assert stored.role == MemberRole.MATCH_MANAGER


def test_batches_get_distinct_accounts() -> None:
    members = OrganizerMemberFactory.create_batch(5)
    roles = ClubRoleFactory.create_batch(5)

    assert len({member.account_id for member in members}) == 5
    assert len({role.account_id for role in roles}) == 5
