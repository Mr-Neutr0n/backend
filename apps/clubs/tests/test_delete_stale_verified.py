"""A delete checks the stored status, not a stale instance's."""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import pytest
from django.contrib.admin.models import DELETION, LogEntry
from django.contrib.messages import get_messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.clubs.admin import OrganizerAdmin
from apps.clubs.models import Organizer
from apps.clubs.services import verify_organizer

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser() -> "_User":
    account: _User = UserFactory.create(is_staff=True, is_superuser=True)
    return account


@pytest.fixture
def superuser_client(client: Client, superuser: "_User") -> Client:
    client.force_login(superuser)
    return client


def _verify_after_check(
    monkeypatch: pytest.MonkeyPatch, organizer: Organizer, verifier: "_User"
) -> None:
    """Verify ``organizer`` right after the admin's up-front delete check.

    That is the moment between the confirmation page's read and the delete.
    """
    original = OrganizerAdmin.get_deleted_objects

    def check_then_verify(
        self: OrganizerAdmin,
        objs: Sequence[Organizer] | QuerySet[Organizer],
        request: HttpRequest,
    ) -> Any:
        result = original(self, objs, request)
        verify_organizer(Organizer.objects.get(pk=organizer.pk), actor=verifier)
        return result

    monkeypatch.setattr(OrganizerAdmin, "get_deleted_objects", check_then_verify)


def test_stale_unverified_instance_cannot_delete_verified_row(
    superuser: "_User",
) -> None:
    organizer = Organizer.objects.create(name="Made-up Events")
    stale = Organizer.objects.get(pk=organizer.pk)
    verify_organizer(organizer, actor=superuser)

    with pytest.raises(ValueError, match="unverify"):
        stale.delete()

    assert Organizer.objects.get(pk=organizer.pk).is_verified is True


def test_delete_selected_refuses_row_verified_after_check(
    superuser_client: Client, superuser: "_User", monkeypatch: pytest.MonkeyPatch
) -> None:
    organizer = Organizer.objects.create(name="Made-up Person Name")
    _verify_after_check(monkeypatch, organizer, UserFactory.create(is_superuser=True))

    response = superuser_client.post(
        reverse("admin:clubs_organizer_changelist"),
        {
            "action": "delete_selected",
            "_selected_action": [str(organizer.pk)],
            "post": "yes",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert Organizer.objects.filter(pk=organizer.pk).exists()
    assert not LogEntry.objects.filter(action_flag=DELETION).exists()
    messages = [str(message) for message in get_messages(response.wsgi_request)]
    text = " ".join(messages)
    assert organizer.public_code in text
    assert "Made-up Person Name" not in text
    assert not any("Successfully deleted" in message for message in messages)


def test_delete_view_refuses_row_verified_after_check(
    superuser_client: Client, superuser: "_User", monkeypatch: pytest.MonkeyPatch
) -> None:
    organizer = Organizer.objects.create(name="Made-up Person Name")
    _verify_after_check(monkeypatch, organizer, UserFactory.create(is_superuser=True))

    response = superuser_client.post(
        reverse("admin:clubs_organizer_delete", args=[organizer.pk]),
        {"post": "yes"},
        follow=True,
    )

    assert response.status_code == 200
    assert Organizer.objects.filter(pk=organizer.pk).exists()
    assert not LogEntry.objects.filter(action_flag=DELETION).exists()
    messages = [str(message) for message in get_messages(response.wsgi_request)]
    text = " ".join(messages)
    assert organizer.public_code in text
    assert "Made-up Person Name" not in text
    assert not any("deleted successfully" in message for message in messages)
