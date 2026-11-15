"""An Audit Event can record the Partner Application that acted."""

import pytest
from django.contrib import admin
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditAction, AuditEvent
from apps.audit.services import record_event
from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db


def test_record_event_stores_the_application() -> None:
    application = PartnerApplicationFactory.create()
    target = UserFactory.create()

    event = record_event(
        action=AuditAction.RATING_EDIT,
        target=target,
        actor_application=application,
    )

    stored = AuditEvent.objects.get(pk=event.pk)
    assert stored.actor_application_id == application.pk
    assert stored.actor_user_id is None


def test_record_event_stores_both_actors() -> None:
    application = PartnerApplicationFactory.create()
    actor = UserFactory.create()

    event = record_event(
        action=AuditAction.RATING_EDIT,
        target=actor,
        actor=actor,
        actor_application=application,
    )

    stored = AuditEvent.objects.get(pk=event.pk)
    assert stored.actor_user_id == actor.pk
    assert stored.actor_application_id == application.pk


def test_record_event_has_no_application_by_default() -> None:
    target = UserFactory.create()

    event = record_event(action=AuditAction.RATING_EDIT, target=target)

    assert AuditEvent.objects.get(pk=event.pk).actor_application_id is None


def test_record_event_rejects_an_unsaved_application() -> None:
    target = UserFactory.create()
    application = PartnerApplication(name="Made-up Unsaved App")

    with pytest.raises(ValueError, match="application must be saved"):
        record_event(
            action=AuditAction.RATING_EDIT,
            target=target,
            actor_application=application,
        )

    assert AuditEvent.objects.count() == 0


def test_application_that_acted_cannot_be_deleted() -> None:
    application = PartnerApplicationFactory.create()
    record_event(
        action=AuditAction.RATING_EDIT,
        target=UserFactory.create(),
        actor_application=application,
    )

    with pytest.raises(ProtectedError):
        application.delete()


def test_admin_shows_the_application_read_only(client: Client) -> None:
    application = PartnerApplicationFactory.create()
    event = record_event(
        action=AuditAction.RATING_EDIT,
        target=UserFactory.create(),
        actor_application=application,
    )
    client.force_login(UserFactory.create(is_staff=True, is_superuser=True))

    response = client.get(reverse("admin:audit_auditevent_change", args=[event.pk]))

    assert response.status_code == 200
    model_admin = admin.site._registry[AuditEvent]
    assert "actor_application" in model_admin.get_fields(response.wsgi_request)
    assert "actor_application" in model_admin.get_readonly_fields(response.wsgi_request)
    assert application.client_id.encode() in response.content


def test_record_event_rejects_another_model_as_application() -> None:
    target = UserFactory.create()

    with pytest.raises(ValueError, match="PartnerApplication"):
        record_event(
            action=AuditAction.RATING_EDIT,
            target=target,
            actor_application=target,  # type: ignore[arg-type]
        )

    assert AuditEvent.objects.count() == 0
