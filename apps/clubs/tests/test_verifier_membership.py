"""The Account that verified an Organizer cannot become its member."""

from typing import TYPE_CHECKING

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import MemberRole, Organizer, OrganizerMember
from apps.clubs.services import unverify_organizer, verify_organizer

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

pytestmark = pytest.mark.django_db


@pytest.fixture
def verifier() -> "_User":
    account: _User = UserFactory.create(is_staff=True, is_superuser=True)
    return account


@pytest.fixture
def organizer(verifier: "_User") -> Organizer:
    organizer = Organizer.objects.create(name="Made-up Events")
    verify_organizer(organizer, actor=verifier)
    return organizer


def _messages(error: ValidationError) -> str:
    return " ".join(
        message for messages in error.message_dict.values() for message in messages
    )


def test_create_member_as_verifier_is_refused(
    organizer: Organizer, verifier: "_User"
) -> None:
    with pytest.raises(ValidationError):
        OrganizerMember.objects.create(
            organizer=organizer, account=verifier, role=MemberRole.ADMIN
        )

    assert not OrganizerMember.objects.exists()


def test_full_clean_refuses_verifier_on_account(
    organizer: Organizer, verifier: "_User"
) -> None:
    member = OrganizerMember(
        organizer=organizer, account=verifier, role=MemberRole.ADMIN
    )

    with pytest.raises(ValidationError) as error:
        member.full_clean()

    assert "account" in error.value.message_dict
    assert verifier.email not in _messages(error.value)


def test_full_clean_with_unset_links_does_not_crash() -> None:
    member = OrganizerMember(role=MemberRole.ADMIN)

    with pytest.raises(ValidationError) as error:
        member.full_clean()

    assert "organizer" in error.value.message_dict
    assert "account" in error.value.message_dict


def test_changing_member_account_to_verifier_is_refused(
    organizer: Organizer, verifier: "_User"
) -> None:
    member = OrganizerMember.objects.create(
        organizer=organizer, account=UserFactory.create(), role=MemberRole.ADMIN
    )

    member.account = verifier
    with pytest.raises(ValidationError):
        member.save()

    assert OrganizerMember.objects.get(pk=member.pk).account_id != verifier.pk


def test_other_accounts_can_join(organizer: Organizer) -> None:
    account = UserFactory.create()

    OrganizerMember.objects.create(
        organizer=organizer, account=account, role=MemberRole.MATCH_MANAGER
    )

    assert organizer.members.count() == 1


def test_after_unverify_the_verifier_can_join(
    organizer: Organizer, verifier: "_User"
) -> None:
    unverify_organizer(organizer, actor=verifier)

    OrganizerMember.objects.create(
        organizer=organizer, account=verifier, role=MemberRole.ADMIN
    )

    assert organizer.members.filter(account=verifier).exists()


def test_admin_inline_refuses_verifier_with_form_error(
    client: Client, organizer: Organizer, verifier: "_User"
) -> None:
    client.force_login(verifier)
    url = reverse("admin:clubs_organizer_change", args=[organizer.pk])

    response = client.post(
        url,
        {
            "name": organizer.name,
            "members-TOTAL_FORMS": "1",
            "members-INITIAL_FORMS": "0",
            "members-MIN_NUM_FORMS": "0",
            "members-MAX_NUM_FORMS": "1000",
            "members-0-id": "",
            "members-0-organizer": str(organizer.pk),
            "members-0-account": str(verifier.pk),
            "members-0-role": MemberRole.ADMIN,
        },
    )

    assert response.status_code == 200
    assert "errorlist" in response.content.decode()
    assert not OrganizerMember.objects.exists()
