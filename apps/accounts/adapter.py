"""OPEN's django-allauth account adapter (``ACCOUNT_ADAPTER``)."""

from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.http import HttpRequest

from apps.accounts.validators import (
    is_canonical_email,
    normalize_email_address,
    normalized_email_errors,
)


class AccountAdapter(DefaultAccountAdapter):
    """allauth's account adapter, with OPEN's email rules (ADR 0003)."""

    def clean_email(self, email: str) -> str:
        """Normalize an address, then apply the Account email rules to it.

        allauth calls this for every address it takes in: sign-up, adding or
        changing an address, and password reset. The address is normalized
        like the manager does (NFKC, strip, lowercase per character), then
        checked for ASCII, length, and format, in that order. The error
        carries the rule's fixed message, never the submitted value.
        """
        normalized = normalize_email_address(email)
        errors = normalized_email_errors(normalized)
        if errors:
            raise errors[0]
        cleaned: str = super().clean_email(normalized)
        return cleaned

    def authenticate(
        self, request: HttpRequest, **credentials: Any
    ) -> AbstractBaseUser | None:
        """Refuse a non-canonical address before any backend sees it.

        Both backends normalize the address and so would find the Account
        for a variant that NFKC folds onto its address (U+017F long s, or
        fullwidth letters). allauth would then treat the variant as a new,
        unverified address of that Account. A variant is no Account's login
        (ADR 0003), so it fails like a wrong password: the login rate limit
        is still consumed, the password is still hashed (the same time as a
        miss), and no backend runs.
        """
        email = credentials.get("email")
        if isinstance(email, str) and not is_canonical_email(email):
            self.pre_authenticate(request, **credentials)
            get_user_model()().set_password(credentials.get("password"))
            self.authentication_failed(request, **credentials)
            return None
        user: AbstractBaseUser | None = super().authenticate(request, **credentials)
        return user
