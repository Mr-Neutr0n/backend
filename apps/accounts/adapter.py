"""OPEN's django-allauth account adapter (``ACCOUNT_ADAPTER``)."""

from allauth.account.adapter import DefaultAccountAdapter

from apps.accounts.validators import normalize_email_address, normalized_email_errors


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
