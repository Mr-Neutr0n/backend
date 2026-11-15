"""Admin for Clubs and Organizers.

Verification is read-only on the change form. It changes only through the
verify and unverify actions, which call ``apps.clubs.services`` and are
shown only to Accounts with ``clubs.verify_organizer``.
"""

from collections.abc import Callable, Sequence
from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.clubs.models import Club, ClubRole, Organizer, OrganizerMember
from apps.clubs.services import (
    VERIFY_PERMISSION,
    NotAllowedToVerify,
    unverify_organizer,
    verify_organizer,
)

ADMIN_REASON = "Changed through the admin."


class OrganizerMemberInline(admin.TabularInline[OrganizerMember, Organizer]):
    model = OrganizerMember
    extra = 0
    autocomplete_fields = ("account",)


class ClubRoleInline(admin.TabularInline[ClubRole, Club]):
    model = ClubRole
    extra = 0
    autocomplete_fields = ("account",)


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin[Club]):
    list_display = ("public_code", "name", "city", "region")
    readonly_fields = ("public_code",)
    search_fields = ("public_code", "name")
    inlines = (ClubRoleInline,)


@admin.register(Organizer)
class OrganizerAdmin(admin.ModelAdmin[Organizer]):
    list_display = ("public_code", "name", "is_verified")
    readonly_fields = ("public_code", "verified_at", "verified_by")
    search_fields = ("public_code", "name")
    inlines = (OrganizerMemberInline,)
    actions = ("verify_selected", "unverify_selected")

    def get_deleted_objects(
        self, objs: Sequence[Organizer] | QuerySet[Organizer], request: HttpRequest
    ) -> tuple[list[Any], dict[str, int], set[str], list[Any]]:
        """Mark every verified Organizer as protected.

        The delete view and ``delete_selected`` then show "Cannot delete"
        and delete, log, and report nothing. Unverify it first: that
        records an Audit Event, which a delete would not.
        """
        to_delete, model_count, perms_needed, protected = super().get_deleted_objects(
            objs, request
        )
        protected = list(protected)
        for organizer in objs:
            if organizer.is_verified:
                # The OPEN Code only: the name may be a person's.
                protected.append(
                    f"Organizer {organizer.public_code} is verified: unverify it first."
                )
        return to_delete, model_count, perms_needed, protected

    def has_verify_permission(self, request: HttpRequest) -> bool:
        """Django shows an action marked ``permissions=["verify"]`` only
        when this is True.
        """
        return request.user.has_perm(VERIFY_PERMISSION)

    @admin.display(boolean=True, description="Verified")
    def is_verified(self, organizer: Organizer) -> bool:
        return organizer.is_verified

    @admin.action(permissions=["verify"], description="Verify selected organizers")
    def verify_selected(
        self, request: HttpRequest, queryset: QuerySet[Organizer]
    ) -> None:
        self._apply(request, queryset, verify_organizer, "verified")

    @admin.action(
        permissions=["verify"], description="Remove verification from selected"
    )
    def unverify_selected(
        self, request: HttpRequest, queryset: QuerySet[Organizer]
    ) -> None:
        self._apply(request, queryset, unverify_organizer, "unverified")

    def _apply(
        self,
        request: HttpRequest,
        queryset: QuerySet[Organizer],
        change: Callable[..., Organizer],
        done: str,
    ) -> None:
        count = 0
        for organizer in queryset.order_by("pk"):
            try:
                change(organizer, actor=request.user, reason=ADMIN_REASON)
            except NotAllowedToVerify:
                # The OPEN Code only: the name may be a person's.
                self.message_user(
                    request,
                    f"{organizer.public_code} was not changed: you may not "
                    "verify or unverify it.",
                    level=messages.WARNING,
                )
                continue
            count += 1
        if count:
            self.message_user(request, f"{count} organizer(s) {done}.")
