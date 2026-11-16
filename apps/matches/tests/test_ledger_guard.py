"""The ORM refuses to change or delete ledger rows (#26, hard rule 3).

A Match may be saved again only to change its status, through the
workflow services. Its participants and games are never saved again.
None of the three can be deleted, and the bulk query paths are refused
for all of them. Raw SQL is not guarded.
"""

from collections.abc import Callable
from typing import Any

import pytest
from django.db import models

from apps.matches.models import (
    Game,
    Match,
    MatchImmutable,
    MatchParticipant,
    MatchStatus,
)
from apps.matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db

LEDGER_MODELS: tuple[type[models.Model], ...] = (Match, MatchParticipant, Game)


@pytest.fixture
def match() -> Match:
    made: Match = MatchFactory.create()
    return made


def _row(model: type[models.Model], match: Match) -> models.Model:
    if model is Match:
        return match
    row = model._default_manager.filter(match=match).first()
    assert row is not None
    return row


def test_the_factory_match_has_its_rows(match: Match) -> None:
    assert match.participants.count() == 2
    assert match.games.exists()
    assert match.fingerprint


@pytest.mark.parametrize("model", LEDGER_MODELS)
def test_deleting_an_instance_is_refused(
    match: Match, model: type[models.Model]
) -> None:
    row = _row(model, match)

    with pytest.raises(MatchImmutable):
        row.delete()

    assert model._default_manager.filter(pk=row.pk).exists()


def test_deleting_a_match_without_rows_is_refused() -> None:
    bare: Match = MatchFactory.create(games=False, participants=False)

    with pytest.raises(MatchImmutable):
        bare.delete()

    assert Match.objects.filter(pk=bare.pk).exists()


QUERYSET_CALLS: dict[str, Callable[[models.QuerySet[Any]], object]] = {
    "update": lambda queryset: queryset.update(pk=0),
    "delete": lambda queryset: queryset.delete(),
    "bulk_update": lambda queryset: queryset.bulk_update(list(queryset), ["pk"]),
}


@pytest.mark.parametrize("model", LEDGER_MODELS)
@pytest.mark.parametrize("call", sorted(QUERYSET_CALLS))
def test_bulk_queryset_changes_are_refused(
    match: Match, model: type[models.Model], call: str
) -> None:
    queryset = model._default_manager.all()

    with pytest.raises(MatchImmutable):
        QUERYSET_CALLS[call](queryset)


@pytest.mark.parametrize("model", LEDGER_MODELS)
def test_an_upsert_is_refused(match: Match, model: type[models.Model]) -> None:
    with pytest.raises(MatchImmutable):
        model._default_manager.bulk_create(
            [], update_conflicts=True, update_fields=["pk"], unique_fields=["pk"]
        )


@pytest.mark.parametrize("model", LEDGER_MODELS)
def test_the_base_manager_is_guarded(match: Match, model: type[models.Model]) -> None:
    with pytest.raises(MatchImmutable):
        model._base_manager.all().update(pk=0)


def test_a_full_save_of_a_match_is_refused(match: Match) -> None:
    match.location = "Made-up Park"

    with pytest.raises(MatchImmutable):
        match.save()

    assert Match.objects.get(pk=match.pk).location == ""


@pytest.mark.parametrize(
    "update_fields", [["location"], ["status", "location"], ["fingerprint"], []]
)
def test_saving_fields_other_than_status_is_refused(
    match: Match, update_fields: list[str]
) -> None:
    with pytest.raises(MatchImmutable):
        match.save(update_fields=update_fields)


def test_saving_only_the_status_is_allowed(match: Match) -> None:
    match.status = MatchStatus.CONFIRMED

    match.save(update_fields=["status"])

    assert Match.objects.get(pk=match.pk).status == MatchStatus.CONFIRMED


@pytest.mark.parametrize("model", [MatchParticipant, Game])
@pytest.mark.parametrize("update_fields", [None, ["match"]])
def test_saving_an_existing_row_is_refused(
    match: Match, model: type[models.Model], update_fields: list[str] | None
) -> None:
    row = _row(model, match)

    with pytest.raises(MatchImmutable):
        row.save(update_fields=update_fields)


def test_the_message_is_fixed(match: Match) -> None:
    with pytest.raises(MatchImmutable) as error:
        match.delete()

    assert str(error.value) == MatchImmutable.message
