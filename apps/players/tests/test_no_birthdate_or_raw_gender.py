"""No model or fixture stores a full birthdate or a raw gender (ADR 0009)."""

from collections.abc import Iterable
from pathlib import Path

from django.apps import apps
from django.db import models
from django.test.utils import isolate_apps

APPS_DIR = Path(__file__).resolve().parents[2]

RAW_GENDER_NAMES = {"gender", "sex"}


def _offending_fields(model_classes: Iterable[type[models.Model]]) -> list[str]:
    found: list[str] = []
    for model in model_classes:
        for field in model._meta.get_fields():
            name = field.name.lower()
            label = f"{model._meta.label}.{field.name}"
            if isinstance(field, models.DateField) and "birth" in name:
                # DateTimeField is a DateField subclass.
                found.append(label)
            if name in RAW_GENDER_NAMES:
                found.append(label)
    return found


def test_no_installed_model_has_a_birthdate_or_raw_gender_field() -> None:
    assert _offending_fields(apps.get_models()) == []


def test_player_stores_birth_year_and_month_only() -> None:
    player = apps.get_model("players", "Player")
    names = {field.name for field in player._meta.get_fields()}

    assert {name for name in names if "birth" in name} == {
        "birth_year",
        "birth_month",
    }
    assert {name for name in names if "gender" in name} == {"gender_division"}


@isolate_apps("apps.players")
def test_scan_catches_a_birthdate_and_a_raw_gender() -> None:
    class Bad(models.Model):
        date_of_birth = models.DateField()
        birth_moment = models.DateTimeField()
        gender = models.CharField(max_length=8)
        sex = models.CharField(max_length=8)

        def __str__(self) -> str:
            return "bad"

    assert _offending_fields([Bad]) == [
        "players.Bad.date_of_birth",
        "players.Bad.birth_moment",
        "players.Bad.gender",
        "players.Bad.sex",
    ]


def test_no_fixtures_under_apps() -> None:
    # No fixtures exist today. A fixture added later must not carry a
    # birthdate or a raw gender: extend this test when one lands.
    assert sorted(APPS_DIR.glob("**/fixtures/*")) == []
