"""OPEN's django-allauth authentication backend."""

from allauth.account.auth_backends import AuthenticationBackend as BaseBackend
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser


class AuthenticationBackend(BaseBackend):
    """allauth's backend, finding an Account only through its manager.

    allauth's own lookup matches the lowercased input exactly against every
    EmailAddress row and User.email. ADR 0003 makes User.email the login and
    allows one identity lookup only: the manager's ``get_by_natural_key``,
    which normalizes the input and compares with the unique constraint's
    ``Lower("email")``. A lookalike address, or a second EmailAddress row
    such as a pending change of address, never reaches an Account.

    The parent still checks the password and ``user_can_authenticate``
    (``is_active``), and hashes the password anyway when no Account matches,
    so a miss takes as long as a wrong password.
    """

    def _authenticate_by_email(
        self, email: str, password: str
    ) -> AbstractBaseUser | None:
        if not email:
            return None
        manager = get_user_model()._default_manager
        try:
            user = manager.get_by_natural_key(email)
        except manager.model.DoesNotExist:
            return None
        checked: AbstractBaseUser | None = self._check_password(user, password)
        return checked
