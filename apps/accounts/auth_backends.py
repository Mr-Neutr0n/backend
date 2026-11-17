"""OPEN's django-allauth authentication backend."""

from allauth.account.auth_backends import AuthenticationBackend as BaseBackend


class AuthenticationBackend(BaseBackend):
    """allauth's backend, finding Accounts through the manager."""
