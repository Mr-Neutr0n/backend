"""The fingerprint constraint's name says what it does: unique unless voided.

A pending Match is not counted (CONTEXT.md, Ledger), so "while counted"
was wrong (review round 1, T7).
"""

from apps.matches import services
from apps.matches.models import Match

NAME = "matches_match_fingerprint_unique_unless_voided"


def test_constraint_is_named_unless_voided() -> None:
    names = {constraint.name for constraint in Match._meta.constraints}

    assert NAME in names
    assert not any("counted" in name for name in names)


def test_service_converts_the_renamed_constraint() -> None:
    assert services._FINGERPRINT_CONSTRAINT == NAME
