"""OPEN's django-allauth headless adapter (``HEADLESS_ADAPTER``)."""

import dataclasses
from typing import Any

from allauth.account.models import EmailAddress
from allauth.account.utils import user_display
from allauth.headless.adapter import DefaultHeadlessAdapter
from django.contrib.auth.base_user import AbstractBaseUser

# Never in a user payload: the API exposes no row id (CLAUDE.md, Public
# identifiers), and an Account has no username.
_HIDDEN_FIELDS = frozenset({"id", "username"})


class HeadlessAdapter(DefaultHeadlessAdapter):
    """allauth's headless adapter, without a row id in user payloads.

    allauth builds both the user object in its responses and the User
    schema in its OpenAPI document from ``get_user_dataclass()``, so the id
    is dropped there and never filled in ``user_as_dataclass()``.
    """

    def get_user_dataclass(self) -> type[Any]:
        base = super().get_user_dataclass()
        fields = [
            (field.name, field.type, dataclasses.field(metadata=field.metadata))
            for field in dataclasses.fields(base)
            if field.name not in _HIDDEN_FIELDS
        ]
        return dataclasses.make_dataclass("User", fields)

    def user_as_dataclass(self, user: AbstractBaseUser) -> Any:
        email = EmailAddress.objects.get_primary_email(user) if user.pk else None
        return self.get_user_dataclass()(
            display=user_display(user),
            email=email or None,
            has_usable_password=user.has_usable_password(),
        )
