"""A verified Organizer cannot be deleted: unverify it first, which is audited."""

from typing import TYPE_CHECKING

import pytest
from django.contrib.admin.models import DELETION, LogEntry
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Organizer
from apps.clubs.services import verify_organizer

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

pytestmark = pytest.mark.django_db

CHANGELIST = "admin:clubs_organizer_changelist"


@pytest.fixture
def superuser() -> "_User":
    account: _User = UserFactory.create(is_staff=True, is_superuser=True)
    return account


@pytest.fixture
def superuser_client(client: Client, superuser: "_User") -> Client:
    client.force_login(superuser)
    return client


def _organizer(verified_by: "_User | None" = None) -> Organizer:
    organizer = Organizer.objects.create(name="Made-up Events")
    if verified_by is not None:
        verify_organizer(organizer, actor=verified_by)
    return organizer


def _deletion_logged() -> bool:
    return LogEntry.objects.filter(action_flag=DELETION).exists()


def test_model_delete_of_verified_organizer_raises(superuser: "_User") -> None:
    organizer = _organizer(verified_by=superuser)

    with pytest.raises(ValueError, match="unverify"):
        organizer.delete()

    assert Organizer.objects.filter(pk=organizer.pk).exists()


def test_model_delete_of_unverified_organizer_works() -> None:
    organizer = _organizer()

    organizer.delete()

    assert not Organizer.objects.exists()


def test_delete_view_keeps_verified_organizer(
    superuser_client: Client, superuser: "_User"
) -> None:
    organizer = _organizer(verified_by=superuser)
    url = reverse("admin:clubs_organizer_delete", args=[organizer.pk])

    response = superuser_client.post(url, {"post": "yes"})

    assert response.status_code == 200
    assert "Cannot delete" in response.content.decode()
    assert Organizer.objects.get(pk=organizer.pk).is_verified is True
    assert not _deletion_logged()


def test_delete_selected_keeps_verified_organizer(
    superuser_client: Client, superuser: "_User"
) -> None:
    verified = _organizer(verified_by=superuser)
    unverified = _organizer()

    response = superuser_client.post(
        reverse(CHANGELIST),
        {
            "action": "delete_selected",
            "_selected_action": [str(verified.pk), str(unverified.pk)],
            "post": "yes",
        },
    )

    assert response.status_code == 200
    assert "Cannot delete" in response.content.decode()
    assert Organizer.objects.count() == 2
    assert not _deletion_logged()


def test_delete_view_removes_unverified_organizer(superuser_client: Client) -> None:
    organizer = _organizer()
    url = reverse("admin:clubs_organizer_delete", args=[organizer.pk])

    response = superuser_client.post(url, {"post": "yes"})

    assert response.status_code == 302
    assert not Organizer.objects.exists()
    assert _deletion_logged()


def test_delete_selected_removes_unverified_organizers(
    superuser_client: Client,
) -> None:
    organizers = [_organizer(), _organizer()]

    response = superuser_client.post(
        reverse(CHANGELIST),
        {
            "action": "delete_selected",
            "_selected_action": [str(o.pk) for o in organizers],
            "post": "yes",
        },
    )

    assert response.status_code == 302
    assert not Organizer.objects.exists()
