"""allauth's EmailAddress has no admin (issue #30, ADR 0009).

Its __str__ returns the address, so the admin log's object_repr would
hold an identifying field.
"""

from allauth.account.models import EmailAddress
from django.contrib import admin


def test_email_address_admin_is_unregistered() -> None:
    assert not admin.site.is_registered(EmailAddress)
