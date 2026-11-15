"""Create Players and change their profile fields and privacy settings.

Only the player changes their own Player (ADR 0009). ``update_profile`` and
``update_privacy`` refuse any other actor before writing anything. Each
change records one Audit Event in the same transaction. A profile change
records only the changed field names, never a value, because these are
identifying personal data fields (ADR 0009). A privacy change records the
changed settings' levels.
"""

from collections.abc import Mapping
from typing import TYPE_CHECKING

from django.contrib.auth.models import AnonymousUser
from django.db import transaction

from apps.audit.models import AuditAction
from apps.audit.services import record_event, snapshot
from apps.players.models import Player, PlayerPrivacy

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

PROFILE_FIELDS: tuple[str, ...] = (
    "display_name",
    "legal_name",
    "birth_year",
    "birth_month",
    "gender_division",
    "city",
    "region",
)


class NotOwnPlayer(PermissionError):
    """The actor is not the Player's own active Account."""


def create_player(
    *,
    account: "_User",
    display_name: str,
    birth_year: int | None,
    birth_month: int | None,
    legal_name: str = "",
    gender_division: str = "",
    city: str = "",
    region: str = "",
) -> Player:
    """Create a Player for ``account``, with default privacy settings.

    Raises ``ValidationError`` for an invalid or missing value, or when the
    Account already has a Player. Records no Audit Event: creating a
    Player changes no privacy setting. The 13-and-older rule is #114.
    """
    with transaction.atomic():
        player = Player(
            account=account,
            display_name=display_name,
            legal_name=legal_name,
            birth_year=birth_year,
            birth_month=birth_month,
            gender_division=gender_division,
            city=city,
            region=region,
        )
        player.full_clean()
        player.save()
        PlayerPrivacy.objects.create(player=player)
    return player


def _refuse_unless_owner(player: Player, actor: "_User | AnonymousUser | None") -> None:
    if (
        actor is None
        or not actor.is_authenticated
        or not actor.is_active
        or actor.pk != player.account_id
    ):
        raise NotOwnPlayer("Only the player can change their own Player.")


def _refuse_unknown(changes: Mapping[str, object], allowed: tuple[str, ...]) -> None:
    unknown = sorted(set(changes) - set(allowed))
    if unknown:
        raise ValueError(f"Not a field that can be changed: {', '.join(unknown)}.")


def update_profile(
    *,
    player: Player,
    actor: "_User | AnonymousUser | None",
    changes: Mapping[str, object],
) -> Player:
    """Apply ``changes`` to the player's profile fields and return the Player.

    Raises ``NotOwnPlayer`` unless ``actor`` is the Player's own active
    Account, ``ValueError`` for a key outside ``PROFILE_FIELDS``, and
    ``ValidationError`` for an invalid value. Nothing is saved or recorded
    when any of these is raised, or when no value changed.
    """
    _refuse_unless_owner(player, actor)
    _refuse_unknown(changes, PROFILE_FIELDS)
    with transaction.atomic():
        locked = Player.objects.select_for_update().get(pk=player.pk)
        old = {name: getattr(locked, name) for name in PROFILE_FIELDS}
        for name, value in changes.items():
            setattr(locked, name, value)
        locked.full_clean()
        changed = sorted(
            name for name in PROFILE_FIELDS if getattr(locked, name) != old[name]
        )
        if changed:
            locked.save(update_fields=changed)
            # Names only: these are identifying fields (ADR 0009).
            record_event(
                action=AuditAction.PLAYER_PROFILE_CHANGE,
                target=locked,
                actor=actor,
                after={"changed_fields": changed},
            )
    player.refresh_from_db()
    return player


def update_privacy(
    *,
    player: Player,
    actor: "_User | AnonymousUser | None",
    changes: Mapping[str, object],
) -> PlayerPrivacy:
    """Apply ``changes`` to the player's privacy settings and return them.

    Raises like ``update_profile``, with keys checked against
    ``PlayerPrivacy.SETTINGS``. The Audit Event targets the Player, so it
    is one of the events about that player (#39).
    """
    _refuse_unless_owner(player, actor)
    _refuse_unknown(changes, PlayerPrivacy.SETTINGS)
    with transaction.atomic():
        privacy = PlayerPrivacy.objects.select_for_update().get(player=player)
        old = snapshot(privacy, PlayerPrivacy.SETTINGS)
        for name, value in changes.items():
            setattr(privacy, name, value)
        privacy.full_clean()
        new = snapshot(privacy, PlayerPrivacy.SETTINGS)
        changed = sorted(
            name for name in PlayerPrivacy.SETTINGS if new[name] != old[name]
        )
        if changed:
            privacy.save(update_fields=changed)
            record_event(
                action=AuditAction.PRIVACY_CHANGE,
                target=player,
                actor=actor,
                before={name: old[name] for name in changed},
                after={name: new[name] for name in changed},
            )
    return privacy
