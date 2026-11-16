"""Expiring unconfirmed matches (#26, acceptance criterion 9). Made-up data."""

from datetime import date, timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEvent
from apps.matches.models import FlagReason, Match, MatchFlag, MatchStatus
from apps.matches.signals import MatchChange
from apps.matches.tasks import expire_unconfirmed_matches as expire_task
from apps.matches.tests.conftest import SignalLog
from apps.matches.tests.factories import MatchFactory, raw_update
from apps.matches.workflow import expire_unconfirmed_matches
from config import celery_app

pytestmark = pytest.mark.django_db

DAYS = 7


def _match(status: MatchStatus = MatchStatus.PENDING, age_days: int = 30) -> Match:
    made: Match = MatchFactory.create()
    raw_update(
        made,
        status=status,
        created_at=timezone.now() - timedelta(days=age_days),
    )
    return made


def _status(match: Match) -> str:
    return Match.objects.get(pk=match.pk).status


def _expire_events() -> list[AuditEvent]:
    return list(AuditEvent.objects.filter(action=AuditAction.MATCH_EXPIRE))


def test_unset_does_nothing() -> None:
    old = _match()

    assert expire_unconfirmed_matches() == 0

    assert _status(old) == MatchStatus.PENDING
    assert _expire_events() == []


@override_settings(MATCH_CONFIRMATION_EXPIRY_DAYS=DAYS)
def test_old_pending_matches_are_voided(signals: SignalLog) -> None:
    old = _match()
    young = _match(age_days=DAYS - 1)
    confirmed = _match(MatchStatus.CONFIRMED)
    disputed = _match(MatchStatus.DISPUTED)

    assert expire_unconfirmed_matches() == 1

    assert _status(old) == MatchStatus.VOIDED
    assert _status(young) == MatchStatus.PENDING
    assert _status(confirmed) == MatchStatus.CONFIRMED
    assert _status(disputed) == MatchStatus.DISPUTED
    [event] = _expire_events()
    assert event.target_object_id == str(old.pk)
    assert event.actor_user is None
    assert event.actor_application is None
    assert event.before == {"status": MatchStatus.PENDING}
    assert event.after == {"status": MatchStatus.VOIDED}
    assert signals.changed == []
    assert signals.confirmed == []


@override_settings(MATCH_CONFIRMATION_EXPIRY_DAYS=DAYS)
def test_a_second_run_voids_nothing_more() -> None:
    _match()
    expire_unconfirmed_matches()

    assert expire_unconfirmed_matches() == 0

    assert len(_expire_events()) == 1


@override_settings(MATCH_CONFIRMATION_EXPIRY_DAYS=DAYS)
def test_now_is_the_reference_time() -> None:
    young = _match(age_days=1)

    later = timezone.now() + timedelta(days=DAYS)

    assert expire_unconfirmed_matches(now=later) == 1
    assert _status(young) == MatchStatus.VOIDED


@override_settings(MATCH_CONFIRMATION_EXPIRY_DAYS=DAYS)
def test_expiry_releases_a_held_match(signals: SignalLog) -> None:
    old = _match()
    held: Match = MatchFactory.create(played_on=date(2026, 5, 1))
    raw_update(held, status=MatchStatus.CONFIRMED)
    MatchFlag.objects.create(
        match=old, reason=FlagReason.POSSIBLE_DUPLICATE, duplicate_of=held
    )

    expire_unconfirmed_matches()

    assert held.is_counted()
    assert signals.changed == [(held.pk, MatchChange.RELEASE, date(2026, 5, 1))]


@override_settings(MATCH_CONFIRMATION_EXPIRY_DAYS=DAYS)
def test_the_task_returns_the_count() -> None:
    _match()

    assert expire_task.delay().get() == 1


def test_the_task_has_an_explicit_name_and_the_default_queue() -> None:
    assert expire_task.name == "apps.matches.tasks.expire_unconfirmed_matches"
    route = celery_app.amqp.router.route({}, expire_task.name)
    assert route["queue"].name == "default"


def test_the_task_stays_under_the_visibility_timeout() -> None:
    timeout = celery_app.conf.broker_transport_options["visibility_timeout"]

    assert expire_task.time_limit is not None
    assert expire_task.soft_time_limit is not None
    assert expire_task.soft_time_limit < expire_task.time_limit < timeout


def test_beat_runs_the_task_daily() -> None:
    entries = [
        entry
        for entry in celery_app.conf.beat_schedule.values()
        if entry["task"] == expire_task.name
    ]

    [entry] = entries
    schedule = entry["schedule"]
    assert schedule.hour == {3}
    assert schedule.minute == {0}
