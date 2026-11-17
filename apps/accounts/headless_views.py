"""OPEN's replacements for some of allauth's headless views (issue #30).

allauth's headless API takes no form classes from settings, so where an
input needs OPEN's rules, the view is subclassed with an OPEN input, and
`headless_urlpatterns()` serves it at allauth's own path, ahead of
allauth's URLconf (`config/urls.py`).

- Password reset request: the Account is found only through the manager's
  `get_by_natural_key` on the canonical address, active Accounts only
  (ADR 0003). allauth matches every EmailAddress row instead.
- Email verification: an address that is another Account's login cannot
  be verified (allauth's `email_taken`, a 400). allauth checks only other
  verified EmailAddress rows, so verifying would set the address as this
  Account's `User.email` and break the unique constraint with a 500.
"""

from typing import TYPE_CHECKING

from allauth.account.adapter import get_adapter
from allauth.headless.account.inputs import (
    RequestPasswordResetInput as BaseRequestPasswordResetInput,
)
from allauth.headless.account.inputs import VerifyEmailInput as BaseVerifyEmailInput
from allauth.headless.account.views import (
    RequestPasswordResetView as BaseRequestPasswordResetView,
)
from allauth.headless.account.views import VerifyEmailView as BaseVerifyEmailView
from allauth.headless.constants import Client
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import URLPattern, path

from apps.accounts.validators import is_canonical_email

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser


def account_for_login(email: str) -> "AbstractBaseUser | None":
    """The active Account whose login is this address, or None.

    Only a canonical address can name an Account, and only through the
    manager's natural key lookup (ADR 0003, CLAUDE.md "Account emails").
    """
    if not is_canonical_email(email):
        return None
    manager = get_user_model()._default_manager
    try:
        account = manager.get_by_natural_key(email)
    except manager.model.DoesNotExist:
        return None
    return account if account.is_active else None


class RequestPasswordResetInput(BaseRequestPasswordResetInput):
    """allauth's reset request, finding the Account by its login only.

    Never raises for the address: an unknown or non-canonical address gets
    the same answer as a known one and no mail (enumeration prevention).
    """

    def clean_email(self) -> str:
        email: str = self.cleaned_data["email"]
        account = account_for_login(email)
        self.users = [account] if account else []
        return email


class RequestPasswordResetView(BaseRequestPasswordResetView):
    input_class = RequestPasswordResetInput


def is_another_accounts_login(email: str, account_id: object) -> bool:
    """Whether the address is the login (User.email) of another Account."""
    manager = get_user_model()._default_manager
    try:
        holder = manager.get_by_natural_key(email)
    except manager.model.DoesNotExist:
        return False
    return bool(holder.pk != account_id)


class VerifyEmailInput(BaseVerifyEmailInput):
    """allauth's verify input, refusing another Account's login.

    The person verifying holds the key mailed to the address, so the
    refusal tells them nothing their mailbox does not (a sign-up with it
    would mail them that an account exists). The message is allauth's
    fixed text and never names the address.
    """

    def clean_key(self) -> str:
        key: str = super().clean_key()
        address = (
            self.process.email_address
            if self.process
            else self.verification.email_address
        )
        if not address.verified and is_another_accounts_login(
            address.email, address.user_id
        ):
            raise get_adapter().validation_error("email_taken")
        return key


class VerifyEmailView(BaseVerifyEmailView):
    input_class = VerifyEmailInput


def headless_urlpatterns() -> list[URLPattern]:
    """OPEN's views at allauth's paths, for each enabled headless client."""
    patterns = []
    for client in (Client.BROWSER, Client.APP):
        if client.value not in settings.HEADLESS_CLIENTS:
            continue
        prefix = f"{client.value}/v1/auth/"
        patterns += [
            path(
                f"{prefix}password/request",
                RequestPasswordResetView.as_api_view(client=client),
            ),
            path(
                f"{prefix}email/verify",
                VerifyEmailView.as_api_view(client=client),
            ),
        ]
    return patterns
