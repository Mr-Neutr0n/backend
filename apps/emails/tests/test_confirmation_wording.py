"""The plain verification email's wording holds for every way it is sent
(issue #36 review).

allauth sends ``account/email/email_confirmation`` (not the sign-up
variant) when an unverified Account tries to sign in, when an address is
added or changed, and when a new link is requested. The text must not
claim someone asked to verify the address. Made-up data only.
"""

from typing import Any

import pytest
from allauth.core import context as allauth_context
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.test import RequestFactory

from apps.accounts.adapter import AccountAdapter
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

TO = "wording-recipient@example.org"
PREFIX = "account/email/email_confirmation"
NEW_REASON = (
    "You received this email because this email address is on an OPEN "
    "account but is not verified yet, and someone signed in with it, added "
    "it to the account, or asked for a new verification link."
)
OLD_REASON = "asked to verify it"
NEW_IGNORE = (
    "If you did not expect this email, you can ignore it. The address stays unverified."
)
OLD_IGNORE = "If you did not ask for this"


def _render() -> EmailMessage:
    request = RequestFactory().get("/")
    ctx: dict[str, Any] = {
        "request": request,
        "email": TO,
        "current_site": get_current_site(request),
        "user": UserFactory.create(email=TO),
        "key": "made-up-key",
        "activate_url": f"{settings.FRONTEND_URL}/account/verify-email/made-up-key",
    }
    with allauth_context.request_context(request):
        message: EmailMessage = AccountAdapter(request).render_mail(PREFIX, TO, ctx)
    return message


def test_plain_verification_email_fits_a_sign_in_or_a_new_address() -> None:
    message = _render()
    [(html, _)] = getattr(message, "alternatives", [])

    for body in (str(message.body), str(html)):
        assert NEW_REASON in body
        assert OLD_REASON not in body
        assert NEW_IGNORE in body
        assert OLD_IGNORE not in body
        assert "Please verify your email address for OPEN." in body
