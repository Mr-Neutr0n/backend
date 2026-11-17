"""OPEN's django-allauth account adapter."""

from allauth.account.adapter import DefaultAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    """allauth's account adapter, with OPEN's email rules."""
