"""`is_canonical_email` (issue #30, ADR 0003).

Only a canonical address may name an existing Account at login or password
reset: an ASCII address that stripping and lowercasing already bring to its
stored form, and that passes every email rule.
"""

import pytest

from apps.accounts.validators import EMAIL_MAX_LENGTH, is_canonical_email


@pytest.mark.parametrize(
    "email",
    [
        "sam@example.org",
        " Sam@Example.ORG ",
        "SAM@EXAMPLE.ORG",
    ],
)
def test_canonical_addresses(email: str) -> None:
    assert is_canonical_email(email)


@pytest.mark.parametrize(
    "email",
    [
        "ſam@example.org",  # U+017F LATIN SMALL LETTER LONG S
        "sam@ｅｘａｍｐｌｅ.org",  # fullwidth "example"
        "Kate@example.org",  # U+212A KELVIN SIGN, lowercases to "k"
        "ınfo@example.org",  # U+0131 dotless i, not ASCII once normalized
        "jörg@example.org",  # non-ASCII
        "a" * (EMAIL_MAX_LENGTH - len("@example.org") + 1) + "@example.org",
        "not-an-address",
        "",
    ],
)
def test_non_canonical_addresses(email: str) -> None:
    assert not is_canonical_email(email)
