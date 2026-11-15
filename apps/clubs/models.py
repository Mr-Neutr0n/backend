"""Clubs, Organizers, and the roles that link Accounts to them.

An Organizer's verified status is security-sensitive (CLAUDE.md, hard rule
8): change it only through ``apps.clubs.services``, which checks the actor
and records an Audit Event. The permission rules that use the roles here
are #79.
"""

import unicodedata
from collections.abc import Collection
from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.public_ids.codes import CodeType
from apps.public_ids.models import PublicCodeModel

# Messages never include the submitted value (CLAUDE.md, API). Django's
# defaults for these keys do.
_CHOICE_MESSAGES = {"invalid_choice": "Choose one of the listed options."}
_CONTROL_CHARACTER = "Remove control or invalid characters."
_NOT_TEXT = "Enter text."
# Control characters (Postgres cannot store NUL) and lone surrogates
# (not encodable as UTF-8).
_REFUSED_CATEGORIES = frozenset({"Cc", "Cs"})


def _clean_text_fields(
    instance: models.Model,
    names: Collection[str],
    skip: Collection[str],
) -> dict[str, list[ValidationError]]:
    """Strip the named text fields and refuse control characters.

    Returns the errors by field name. A value that is not a string is
    refused, since Django's own conversion would turn any value into text.
    """
    errors: dict[str, list[ValidationError]] = {}
    for name in names:
        if name in skip:
            continue
        value = getattr(instance, name)
        if not isinstance(value, str):
            errors[name] = [ValidationError(_NOT_TEXT)]
            continue
        value = value.strip()
        setattr(instance, name, value)
        if any(unicodedata.category(char) in _REFUSED_CATEGORIES for char in value):
            errors[name] = [ValidationError(_CONTROL_CHARACTER)]
    return errors


class _CleanedTextModel(PublicCodeModel):
    """Strips and checks ``TEXT_FIELDS`` before Django's field validation."""

    TEXT_FIELDS: ClassVar[tuple[str, ...]] = ()

    class Meta:
        abstract = True

    def clean_fields(self, exclude: Collection[str] | None = None) -> None:
        skip = set(exclude or ())
        errors = _clean_text_fields(self, self.TEXT_FIELDS, skip)
        try:
            super().clean_fields(exclude=skip | set(errors))
        except ValidationError as error:
            errors = error.update_error_dict(errors)
        if errors:
            raise ValidationError(errors)


class MemberRole(models.TextChoices):
    """A role an Account holds at an Organizer or a Club."""

    ADMIN = "admin", "Admin"
    MATCH_MANAGER = "match_manager", "Match manager"


class Club(_CleanedTextModel):
    """A place or group where players play (CONTEXT.md, Club)."""

    public_code_type = CodeType.CLUB
    TEXT_FIELDS: ClassVar[tuple[str, ...]] = ("name", "city", "region")

    name = models.CharField(max_length=200)
    city = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                # Refuses "" and whitespace only.
                condition=~Q(name__regex=r"^\s*$"),
                name="clubs_club_name_not_empty",
            ),
        ]

    def __str__(self) -> str:
        # The OPEN Code, never a name, for one rule with Organizer.
        return self.public_code


class Organizer(_CleanedTextModel):
    """A person or a body that runs events (CONTEXT.md, Organizer).

    A person who organizes alone is an Organizer with one OrganizerMember.
    A verified Organizer's submissions count as confirmed, so change
    ``verified_at`` and ``verified_by`` only through
    ``apps.clubs.services.verify_organizer`` and ``unverify_organizer``. A
    raw write skips the actor checks and the Audit Event.
    """

    public_code_type = CodeType.ORGANIZER
    TEXT_FIELDS: ClassVar[tuple[str, ...]] = ("name",)

    name = models.CharField(max_length=200)
    verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    # PROTECT, like the audit log: an Account that has verified is
    # deactivated, not deleted.
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        editable=False,
    )

    class Meta:
        permissions: ClassVar[list[tuple[str, str]]] = [
            ("verify_organizer", "Can verify or unverify an organizer"),
        ]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=~Q(name__regex=r"^\s*$"),
                name="clubs_organizer_name_not_empty",
            ),
            models.CheckConstraint(
                condition=Q(verified_at__isnull=True, verified_by__isnull=True)
                | Q(verified_at__isnull=False, verified_by__isnull=False),
                name="organizer_verified_pair",
            ),
        ]

    def __str__(self) -> str:
        # The OPEN Code, never the name: it may be a person's (ADR 0009).
        return self.public_code

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None


class OrganizerMember(models.Model):
    """An Account that acts for an Organizer, with its role."""

    organizer = models.ForeignKey(
        Organizer, on_delete=models.CASCADE, related_name="members"
    )
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organizer_memberships",
    )
    role = models.CharField(
        max_length=16, choices=MemberRole, error_messages=_CHOICE_MESSAGES
    )

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["organizer", "account"],
                name="clubs_organizermember_unique_pair",
            ),
            models.CheckConstraint(
                condition=Q(role__in=MemberRole.values),
                name="clubs_organizermember_role_valid",
            ),
        ]

    def __str__(self) -> str:
        # Never the Account's email (CLAUDE.md, Personal data).
        return f"{self.organizer.public_code} {self.role}"


class ClubRole(models.Model):
    """An Account's role at a Club."""

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="roles")
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="club_roles",
    )
    role = models.CharField(
        max_length=16, choices=MemberRole, error_messages=_CHOICE_MESSAGES
    )

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["club", "account"],
                name="clubs_clubrole_unique_pair",
            ),
            models.CheckConstraint(
                condition=Q(role__in=MemberRole.values),
                name="clubs_clubrole_role_valid",
            ),
        ]

    def __str__(self) -> str:
        # Never the Account's email (CLAUDE.md, Personal data).
        return f"{self.club.public_code} {self.role}"
