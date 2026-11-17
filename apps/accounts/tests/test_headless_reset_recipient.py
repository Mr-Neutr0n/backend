"""A password reset key goes only to the Account's stored address
(issue #30, ADR 0003).

The key is mailed to `User.email`, never to the spelling that was
submitted. A submitted address that is not canonical (a variant NFKC folds
onto an Account's address) is treated like an unknown address: the same
200 answer and no mail.
"""

from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.test import Client

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.headless import APP, PASSWORD, RESET_PREFIX, post

pytestmark = pytest.mark.django_db

EMAIL = "sam@example.org"
VARIANTS = [
    "ſam@example.org",  # U+017F LATIN SMALL LETTER LONG S
    "sam@ｅｘａｍｐｌｅ.org",  # fullwidth "example"
]


@pytest.fixture(autouse=True)
def account() -> None:
    """A made-up Account with a verified address."""
    account = UserFactory.create(email=EMAIL, password=PASSWORD)
    EmailAddress.objects.create(user=account, email=EMAIL, primary=True, verified=True)


def _request(email: str) -> Any:
    return post(Client(), f"{APP}/auth/password/request", {"email": email})


def test_the_key_goes_to_the_stored_address_not_the_submitted_spelling() -> None:
    response = _request(" SAM@Example.org ")

    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [EMAIL]
    assert RESET_PREFIX in mail.outbox[0].body


@pytest.mark.parametrize("variant", VARIANTS)
def test_a_variant_is_treated_as_unknown(variant: str) -> None:
    known = _request("nobody@example.org")
    response = _request(variant)

    assert response.status_code == 200
    assert response.json() == known.json()
    assert variant not in response.content.decode()
    assert mail.outbox == []
