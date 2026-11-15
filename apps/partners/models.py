"""Partner Applications: the OAuth clients partners use to reach OPEN.

``PartnerApplication`` is django-oauth-toolkit's swapped Application model
(``OAUTH2_PROVIDER_APPLICATION_MODEL``, decision Q3). Approval decides
whether an application can get production tokens (#29), so it is
security-sensitive (CLAUDE.md, hard rule 8): ``approved_at`` and
``approved_by`` are written only through ``update_fields``, by the
approval service #29 adds.
"""

from typing import Any, ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q
from oauth2_provider.models import AbstractApplication

# Written only through update_fields, by the approval service (#29).
APPROVAL_FIELDS = ("approved_at", "approved_by")


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
        ]

    def __str__(self) -> str:
        # The client_id, never the name: it may name a person.
        return self.client_id

    @property
    def is_approved(self) -> bool:
        return self.approved_at is not None

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save, without writing approval on a full save.

        A full save of an existing application writes every loaded field
        except ``approved_at`` and ``approved_by``, so an instance loaded
        before an approval change cannot write the old status back. A new
        application must start unapproved, so a copy of an approved one is
        refused before any write.

        An explicit ``update_fields`` naming either field writes it with no
        actor check and no Audit Event, as do ``update_or_create`` with
        either in ``defaults`` and every raw write (``QuerySet.update``,
        ``bulk_update``, raw SQL). Only the approval service (#29) may.
        """
        if self._state.adding:
            if self.approved_at is not None or self.approved_by_id is not None:
                raise ValueError(
                    "A new partner application starts unapproved: approve it "
                    "through the approval service."
                )
        elif kwargs.get("update_fields") is None:
            deferred = self.get_deferred_fields()
            kwargs["update_fields"] = [
                field.name
                for field in self._meta.concrete_fields
                if not field.primary_key
                and field.attname not in deferred
                and field.name not in APPROVAL_FIELDS
            ]
        super().save(*args, **kwargs)
