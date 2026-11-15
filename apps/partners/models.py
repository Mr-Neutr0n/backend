"""Partner Applications: the OAuth clients partners use to reach OPEN.

``PartnerApplication`` is django-oauth-toolkit's swapped Application model
(``OAUTH2_PROVIDER_APPLICATION_MODEL``, decision Q3). Approval decides
whether an application can get production tokens (#29), so it is
security-sensitive (CLAUDE.md, hard rule 8): ``approved_at`` and
``approved_by`` are written only through ``update_fields``, by the
approval service #29 adds.
"""

from collections.abc import Collection
from typing import Any, ClassVar, NoReturn, Self

from django.conf import settings
from django.contrib.auth.hashers import identify_hasher
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from oauth2_provider.models import AbstractApplication

# Written only through update_fields, by the approval service (#29).
APPROVAL_FIELDS = ("approved_at", "approved_by")
# Messages never include the submitted value (CLAUDE.md, API).
_BLANK_SECRET = "Enter a client secret."
_HASH_SHAPED_SECRET = (
    "Choose a client secret that does not look like a stored password hash."
)


class PartnerApplication(AbstractApplication):
    """An OAuth client registered by a partner (CONTEXT.md, Partner).

    A new application starts unapproved and in the sandbox. Its client
    secret is always stored hashed: a check constraint refuses
    ``hash_client_secret=False``.
    """

    # PROTECT: an Organizer whose application exists is not deleted out
    # from under it. Null for a platform that is not an Organizer.
    organizer = models.ForeignKey(
        "clubs.Organizer",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="partner_applications",
    )
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    # PROTECT, like Organizer.verified_by: an Account that has approved is
    # deactivated, not deleted.
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        editable=False,
    )
    is_sandbox = models.BooleanField(default=True)

    # Not a field: the client_secret value loaded from the database (or
    # last saved), so only a new or changed value is checked as raw.
    _stored_client_secret: str | None = None

    class Meta(AbstractApplication.Meta):
        swappable = "OAUTH2_PROVIDER_APPLICATION_MODEL"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(approved_at__isnull=True, approved_by__isnull=True)
                | Q(approved_at__isnull=False, approved_by__isnull=False),
                name="partners_application_approved_pair",
            ),
            models.CheckConstraint(
                condition=Q(hash_client_secret=True),
                name="partners_application_secret_hashed",
            ),
            models.CheckConstraint(
                condition=~Q(client_secret=""),
                name="partners_application_secret_not_blank",
            ),
        ]

    def __str__(self) -> str:
        # The client_id, never the name: it may name a person.
        return self.client_id

    @property
    def is_approved(self) -> bool:
        return self.approved_at is not None

    @property
    def get_absolute_url(self) -> NoReturn:
        """Absent: a partner application has no page outside the admin.

        DOT's version reverses its application detail view, which OPEN
        does not mount. Raising AttributeError makes ``hasattr`` false, so
        the admin's ``/admin/r/`` shortcut answers 404, not a 500.
        """
        raise AttributeError("A partner application has no page.")

    @classmethod
    def from_db(
        cls,
        db: str | None,
        field_names: Collection[str],
        values: Collection[Any],
        **kwargs: Any,
    ) -> Self:
        # **kwargs: the stubs add Django 6's fetch_mode, which 5.2 lacks.
        instance = super().from_db(db, field_names, values, **kwargs)
        # Absent when the field is deferred.
        instance._stored_client_secret = instance.__dict__.get("client_secret")
        return instance

    def _raw_secret_error(self) -> str | None:
        """The reason a new or changed client secret is refused, or None.

        A raw secret is hashed on save, so it must not be blank (the hash
        of "" lets a client in with no secret) or look like a hash
        (``ClientSecretField`` would store it as is, and DOT would then
        compare the plaintext). The stored value, unchanged, is a hash and
        is not checked. Neither is a deferred one.
        """
        if "client_secret" in self.get_deferred_fields():
            return None
        secret = self.client_secret
        if not self._state.adding and secret == self._stored_client_secret:
            return None
        if not isinstance(secret, str) or not secret.strip():
            return _BLANK_SECRET
        try:
            identify_hasher(secret)
        except ValueError:
            return None
        return _HASH_SHAPED_SECRET

    def clean_fields(self, exclude: Collection[str] | None = None) -> None:
        skip = set(exclude or ())
        errors: dict[str, list[ValidationError]] = {}
        if "client_secret" not in skip:
            reason = self._raw_secret_error()
            if reason is not None:
                errors["client_secret"] = [ValidationError(reason)]
        try:
            super().clean_fields(exclude=skip | set(errors))
        except ValidationError as error:
            errors = error.update_error_dict(errors)
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save, without writing approval on a full save.

        A full save of an existing application writes every loaded field
        except ``approved_at`` and ``approved_by``, so an instance loaded
        before an approval change cannot write the old status back. A new
        application must start unapproved, so a copy of an approved one is
        refused before any write.

        A new or changed client secret that is blank or looks like a
        password hash is refused before any write (see
        ``_raw_secret_error``). ``QuerySet.update``, ``bulk_create``,
        ``bulk_update``, ``loaddata``, and raw SQL skip that check; the
        database still refuses a blank secret.

        An explicit ``update_fields`` naming either approval field writes
        it with no actor check and no Audit Event, as do
        ``update_or_create`` with either in ``defaults`` and every raw
        write (``QuerySet.update``, ``bulk_create``, ``bulk_update``,
        ``loaddata``, raw SQL). Only the approval service (#29) may.
        """
        update_fields = kwargs.get("update_fields")
        if self._state.adding and (
            self.approved_at is not None or self.approved_by_id is not None
        ):
            raise ValueError(
                "A new partner application starts unapproved: approve it "
                "through the approval service."
            )
        if update_fields is None or "client_secret" in update_fields:
            reason = self._raw_secret_error()
            if reason is not None:
                raise ValueError(f"The client secret is refused: {reason}")
        if self._state.adding and update_fields is None:
            # A new instance given an existing pk would otherwise UPDATE
            # that row, approval included. It fails on the pk instead.
            kwargs.setdefault("force_insert", True)
        elif update_fields is None:
            deferred = self.get_deferred_fields()
            kwargs["update_fields"] = [
                field.name
                for field in self._meta.concrete_fields
                if not field.primary_key
                and field.attname not in deferred
                and field.name not in APPROVAL_FIELDS
            ]
        super().save(*args, **kwargs)
        if "client_secret" not in self.get_deferred_fields():
            # pre_save replaced a raw secret with its hash.
            self._stored_client_secret = self.client_secret


class ClubApplicationGrant(models.Model):
    """A Club's permission for one Partner Application.

    The rules that use it (which application may submit a Club's matches)
    are #79. A grant change records no Audit Event yet.
    """

    club = models.ForeignKey(
        "clubs.Club", on_delete=models.CASCADE, related_name="application_grants"
    )
    application = models.ForeignKey(
        PartnerApplication, on_delete=models.CASCADE, related_name="club_grants"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["club", "application"],
                name="partners_clubapplicationgrant_unique_pair",
            ),
        ]

    def __str__(self) -> str:
        # Codes, never a name (CLAUDE.md, Personal data).
        return f"{self.club.public_code} {self.application.client_id}"
