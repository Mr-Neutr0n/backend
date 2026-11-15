"""The trimmed external ID check agrees with Python's whitespace.

The model strips text with ``str.strip()``, which removes every character
``str.isspace()`` is true for. Postgres ``\\s`` depends on the database
locale and misses some of them (U+00A0, U+202F, U+0085, U+001C), so a raw
write could store "abc" with one of them and count it apart from "abc".
"""

import sys
from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.matches.models import BestOf, Match, MatchFormat
from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db

PYTHON_WHITESPACE = [
    chr(point) for point in range(sys.maxunicode + 1) if chr(point).isspace()
]


@pytest.fixture
def application() -> PartnerApplication:
    made: PartnerApplication = PartnerApplicationFactory.create()
    return made


def _refused(application: PartnerApplication, external_id: str) -> bool:
    """True when the trimmed check, and only it, refuses the raw write."""
    try:
        with transaction.atomic():
            Match.objects.create(
                format=MatchFormat.SINGLES,
                played_on=date(2026, 6, 1),
                best_of=BestOf.ONE,
                submitted_by_application=application,
                external_id=external_id,
            )
    except IntegrityError as error:
        return "matches_match_external_id_trimmed" in str(error)
    return False


@pytest.mark.parametrize("space", [" ", " ", "\u0085", "\u001c", "　"])
@pytest.mark.parametrize("where", ["leading", "trailing"])
def test_unicode_whitespace_at_either_end_is_refused(
    application: PartnerApplication, space: str, where: str
) -> None:
    external_id = f"{space}abc" if where == "leading" else f"abc{space}"

    assert _refused(application, external_id)


def test_every_python_whitespace_character_is_refused_at_either_end(
    application: PartnerApplication,
) -> None:
    accepted = [
        f"U+{ord(space):04X} {where}"
        for space in PYTHON_WHITESPACE
        for where, external_id in (
            ("leading", f"{space}abc"),
            ("trailing", f"abc{space}"),
        )
        if not _refused(application, external_id)
    ]

    assert accepted == []


def test_inner_whitespace_is_accepted(application: PartnerApplication) -> None:
    assert not _refused(application, "abc def ghi")
