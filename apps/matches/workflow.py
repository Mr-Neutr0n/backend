"""The match confirmation workflow: every change to a Match after it is created.

Score confirmation is a security-sensitive area (CLAUDE.md, hard rule 8),
and the ledger is append-only (hard rule 3). These services are the only
code that changes a Match's status, and nothing changes any other field
of a Match: an edit voids the old match and creates a corrected one.

States and transitions:

- ``confirm_match``: a participant records their confirmation. A pending
  match becomes confirmed once at least one player of each team has
  confirmed it. A member (either role) of the match's Event's verified
  Organizer, or an approved application that Organizer owns, confirms a
  pending match alone.
- ``dispute_match``: a participant disputes a pending or confirmed match,
  which becomes disputed.
- ``resolve_dispute``: a moderator resolves a disputed match as confirmed
  or voided, with a reason.
- ``void_match``: a moderator, or an actor ``can_change_match`` allows,
  voids a match in any other status.
- ``edit_match``: the same actors void a match and create its correction
  (``corrects`` links it to the old one) in one transaction, through the
  creation core ``record_match`` uses: validation, model rules, locks,
  duplicate checks, and flags. Only a moderator edits a disputed match.
- ``expire_unconfirmed_matches``: with ``MATCH_CONFIRMATION_EXPIRY_DAYS``
  set, voids pending matches older than that.

Each service checks permission first and raises ``MatchActionDenied``
(fixed text) before it reveals anything about the match. It then locks
the match row and checks its state, raising ``MatchStateError`` (fixed
text) for a change the state does not allow. Every transition writes one
Audit Event in its transaction; a repeated action that changes nothing
writes none. Signals (``apps.matches.signals``) are sent inside the
transaction, after the rows and the Audit Event.

Lock order: ``edit_match`` takes its advisory locks before the row lock,
as ``record_match`` does, so the two never wait on each other in opposite
orders. The other services take only the row lock.
"""

import logging
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record_event, snapshot
from apps.matches.models import (
    ConfirmationDecision,
    FlagReason,
    Match,
    MatchConfirmation,
    MatchParticipant,
    MatchStatus,
    Team,
)
from apps.matches.permissions import (
    Actor,
    MatchActionDenied,
    MatchSubmission,
    can_change_match,
    can_confirm_as_organizer,
    can_create_match,
    is_moderator,
    participant_player,
)
from apps.matches.services import (
    audit_actor,
    check_external_id,
    draft_match,
    duplicate_error,
    exact_duplicate,
    insert_draft,
    lock_draft,
)
from apps.matches.signals import MatchChange, match_changed, match_confirmed
from apps.players.models import Player

logger = logging.getLogger(__name__)

_RESOLUTIONS = frozenset({MatchStatus.CONFIRMED, MatchStatus.VOIDED})


class MatchStateError(ValueError):
    """The match's status does not allow this change. Fixed text."""

    message = "This match cannot make this change in its current status."

    def __init__(self) -> None:
        super().__init__(self.message)


def _lock(match: Match) -> Match:
    """The match's row, locked until the transaction ends."""
    return Match.objects.select_for_update().get(pk=match.pk)


def _linked(match: Match) -> list[Match]:
    """Other matches a possible duplicate flag links to ``match``."""
    return list(
        Match.objects.filter(
            Q(
                flags__duplicate_of=match,
                flags__reason=FlagReason.POSSIBLE_DUPLICATE,
            )
            | Q(
                duplicate_flags__match=match,
                duplicate_flags__reason=FlagReason.POSSIBLE_DUPLICATE,
            )
        )
        .exclude(pk=match.pk)
        .distinct()
        .order_by("pk")
    )


def _counting(matches: Iterable[Match]) -> dict[int, tuple[Match, bool]]:
    return {match.pk: (match, match.is_counted()) for match in matches}


def _send_count_changes(before: dict[int, tuple[Match, bool]]) -> None:
    """Send hold or release for each match whose counting changed."""
    for match, counted_before in before.values():
        counted_now = match.is_counted()
        if counted_before == counted_now:
            continue
        match_changed.send(
            sender=Match,
            match=match,
            change=MatchChange.HOLD if counted_before else MatchChange.RELEASE,
            earliest_date=match.played_on,
        )


def _set_status(match: Match, status: MatchStatus) -> dict[str, object]:
    """Save a new status on a locked match. Returns the snapshot before."""
    before = snapshot(match, ["status"])
    match.status = status
    match.save(update_fields=["status"])
    return before


def _saved(match: Match) -> None:
    if match.pk is None:
        raise MatchActionDenied


def _both_teams_confirmed(match: Match) -> bool:
    confirmed_players = MatchConfirmation.objects.filter(
        match=match, decision=ConfirmationDecision.CONFIRM
    ).values("player_id")
    teams = set(
        MatchParticipant.objects.filter(
            match=match, player_id__in=confirmed_players
        ).values_list("team", flat=True)
    )
    return teams >= {Team.A, Team.B}


def _record_decision(
    match: Match, player: Player, decision: ConfirmationDecision
) -> bool:
    """Add the player's decision, unless they already gave it.

    Returns True when it added the row, False when it was already there.
    """
    if MatchConfirmation.objects.filter(
        match=match, player=player, decision=decision
    ).exists():
        return False
    MatchConfirmation.objects.create(match=match, player=player, decision=decision)
    return True


def _confirm(locked: Match, actor: Actor) -> None:
    before = _set_status(locked, MatchStatus.CONFIRMED)
    record_event(
        action=AuditAction.MATCH_CONFIRM,
        target=locked,
        before=before,
        after=snapshot(locked, ["status"]),
        **audit_actor(actor),
    )
    match_confirmed.send(sender=Match, match=locked)


def confirm_match(match: Match, *, actor: Actor) -> Match:
    """Record ``actor``'s confirmation of ``match`` and return the match.

    An organizer (see ``can_confirm_as_organizer``) confirms a pending
    match alone; for a confirmed match it does nothing. A participant adds
    their confirmation to a pending or confirmed match, and a pending match
    becomes confirmed once each team has one. A repeat does nothing. A
    disputed or voided match raises ``MatchStateError``: disputes go to a
    moderator. Anyone else gets ``MatchActionDenied``. An actor who is
    both organizer and participant takes the organizer path.
    """
    _saved(match)
    organizer = can_confirm_as_organizer(actor, match)
    player = None if organizer else participant_player(actor, match)
    if not organizer and player is None:
        raise MatchActionDenied
    with transaction.atomic():
        locked = _lock(match)
        if organizer:
            if locked.status == MatchStatus.CONFIRMED:
                return locked
            if locked.status != MatchStatus.PENDING:
                raise MatchStateError
            _confirm(locked, actor)
            return locked
        assert player is not None
        if locked.status not in (MatchStatus.PENDING, MatchStatus.CONFIRMED):
            raise MatchStateError
        _record_decision(locked, player, ConfirmationDecision.CONFIRM)
        if locked.status == MatchStatus.PENDING and _both_teams_confirmed(locked):
            _confirm(locked, actor)
        return locked


def dispute_match(match: Match, *, actor: Actor, reason: str = "") -> Match:
    """Record a participant's dispute of ``match`` and return the match.

    A pending or confirmed match becomes disputed, with one
    ``match.dispute`` Audit Event, and a match that was counting sends
    ``match_changed`` with ``change=dispute``. A disputed match only gains
    the participant's dispute row. A participant disputes a match at most
    once: a repeat (also after a moderator resolved the dispute as
    confirmed) does nothing. A voided match raises ``MatchStateError``.
    Only a participant may dispute.
    """
    _saved(match)
    player = participant_player(actor, match)
    if player is None:
        raise MatchActionDenied
    with transaction.atomic():
        locked = _lock(match)
        if locked.status == MatchStatus.VOIDED:
            raise MatchStateError
        # A participant disputes a match once. A repeat, even after a
        # moderator resolved the dispute as confirmed, changes nothing.
        added = _record_decision(locked, player, ConfirmationDecision.DISPUTE)
        if not added or locked.status == MatchStatus.DISPUTED:
            return locked
        was_counting = locked.is_counted()
        before = _set_status(locked, MatchStatus.DISPUTED)
        record_event(
            action=AuditAction.MATCH_DISPUTE,
            target=locked,
            before=before,
            after=snapshot(locked, ["status"]),
            reason=reason,
            **audit_actor(actor),
        )
        if was_counting:
            match_changed.send(
                sender=Match,
                match=locked,
                change=MatchChange.DISPUTE,
                earliest_date=locked.played_on,
            )
        return locked


def resolve_dispute(match: Match, *, actor: Actor, outcome: str, reason: str) -> Match:
    """A moderator resolves a disputed match as confirmed or voided.

    ``reason`` is required. Records one ``dispute.outcome`` Audit Event. A
    confirmed outcome sends ``match_confirmed``; a voided one sends
    ``release`` for each match it no longer holds.
    """
    _saved(match)
    if not is_moderator(actor):
        raise MatchActionDenied
    if outcome not in _RESOLUTIONS:
        raise ValueError("Resolve a dispute as confirmed or voided.")
    if not reason.strip():
        raise ValueError("Give a reason for the dispute outcome.")
    with transaction.atomic():
        locked = _lock(match)
        if locked.status != MatchStatus.DISPUTED:
            raise MatchStateError
        linked = _counting(_linked(locked))
        before = _set_status(locked, MatchStatus(outcome))
        record_event(
            action=AuditAction.DISPUTE_OUTCOME,
            target=locked,
            before=before,
            after=snapshot(locked, ["status"]),
            reason=reason,
            **audit_actor(actor),
        )
        if locked.status == MatchStatus.CONFIRMED:
            match_confirmed.send(sender=Match, match=locked)
        _send_count_changes(linked)
        return locked


def _may_change(actor: Actor, match: Match) -> bool:
    return is_moderator(actor) or can_change_match(actor, match)


def _void(
    locked: Match, *, action: AuditAction, actor: Actor | None, reason: str
) -> None:
    """Void a locked match, audit it, and send its signals."""
    was_counting = locked.is_counted()
    linked = _counting(_linked(locked))
    before = _set_status(locked, MatchStatus.VOIDED)
    record_event(
        action=action,
        target=locked,
        before=before,
        after=snapshot(locked, ["status"]),
        reason=reason,
        **audit_actor(actor),
    )
    if was_counting:
        match_changed.send(
            sender=Match,
            match=locked,
            change=MatchChange.VOID,
            earliest_date=locked.played_on,
        )
    _send_count_changes(linked)


def void_match(match: Match, *, actor: Actor, reason: str = "") -> Match:
    """Void ``match``. For a moderator or an actor ``can_change_match`` allows.

    Any status but voided becomes voided, with one ``match.void`` Audit
    Event. A match that was counting sends ``match_changed`` with
    ``change=void``, and each match it no longer holds gets ``release``.
    """
    _saved(match)
    if not _may_change(actor, match):
        raise MatchActionDenied
    with transaction.atomic():
        locked = _lock(match)
        if locked.status == MatchStatus.VOIDED:
            raise MatchStateError
        _void(locked, action=AuditAction.MATCH_VOID, actor=actor, reason=reason)
        return locked


def edit_match(
    match: Match,
    *,
    actor: Actor,
    reason: str = "",
    format: str,
    team_a: Sequence[Player],
    team_b: Sequence[Player],
    games: Sequence[tuple[int, int]],
    played_on: date,
    best_of: int | None = None,
    game_target: int | None = None,
    scoring_type: str | None = None,
    played_at: datetime | None = None,
    played_at_utc_offset: int | None = None,
    location: str = "",
    event_label: str = "",
    bracket_label: str = "",
    sequence: int = 0,
) -> Match:
    """Void ``match`` and create its correction. Returns the new match.

    For a moderator, or an actor ``can_change_match`` allows that may also
    submit the correction (``can_create_match`` for the old match's Event
    and Club and the new players), checked before any validation; only a
    moderator edits a disputed match, and a voided one raises
    ``MatchStateError``. The correction keeps the old match's submitter,
    external id, Event, and Club, links to it through ``corrects``, and is
    confirmed when the old one was confirmed or disputed, else pending. It
    goes through validation, the model rules, and the duplicate checks
    (``MatchValidationError``, ``DuplicateMatchError``), and any error
    rolls everything back. One ``match.edit`` Audit Event on the old match
    records it (no separate ``match.void``). Signals: ``match_changed``
    with ``change=edit`` for an old match that was counting (the earlier
    of the two dates), else ``match_confirmed`` for a confirmed
    correction, and ``hold`` or ``release`` for each other match whose
    counting changed.
    """
    _saved(match)
    moderator = is_moderator(actor)
    if not (moderator or can_change_match(actor, match)):
        raise MatchActionDenied
    stored = Match.objects.select_related(
        "submitted_by_user", "submitted_by_application", "event", "club"
    ).get(pk=match.pk)
    if not moderator:
        # An edit creates a match, so the editor also needs the authority
        # to submit it, checked before any validation.
        submission = MatchSubmission(
            event=stored.event,
            club=stored.club,
            player_ids=frozenset(
                player.pk
                for player in (*team_a, *team_b)
                if isinstance(player, Player) and player.pk is not None
            ),
        )
        if not can_create_match(actor, submission):
            raise MatchActionDenied
    draft = draft_match(
        format=format,
        team_a=team_a,
        team_b=team_b,
        games=games,
        played_on=played_on,
        best_of=best_of,
        game_target=game_target,
        scoring_type=scoring_type,
        submitted_by_user=stored.submitted_by_user,
        submitted_by_application=stored.submitted_by_application,
        external_id=stored.external_id,
        event=stored.event,
        club=stored.club,
        played_at=played_at,
        played_at_utc_offset=played_at_utc_offset,
        location=location,
        event_label=event_label,
        bracket_label=bracket_label,
        sequence=sequence,
    )
    with transaction.atomic():
        lock_draft(draft)
        locked = _lock(match)
        if locked.status == MatchStatus.VOIDED:
            raise MatchStateError
        if locked.status == MatchStatus.DISPUTED and not moderator:
            raise MatchStateError
        old_status = MatchStatus(locked.status)
        was_counting = locked.is_counted()
        others = _linked(locked) + [
            near
            for near in Match.objects.filter(
                played_on=draft.match.played_on,
                participants__player_id__in=draft.keys_a + draft.keys_b,
            )
            .exclude(status=MatchStatus.VOIDED)
            .exclude(pk=locked.pk)
            .distinct()
        ]
        counting = _counting(others)
        before = _set_status(locked, MatchStatus.VOIDED)

        check_external_id(draft, replaces=locked)
        existing = exact_duplicate(draft)
        if existing is not None:
            raise duplicate_error(existing, actor, reveal=moderator)
        new_status = (
            MatchStatus.PENDING
            if old_status == MatchStatus.PENDING
            else MatchStatus.CONFIRMED
        )
        corrected, _held = insert_draft(draft, status=new_status, corrects=locked)
        record_event(
            action=AuditAction.MATCH_EDIT,
            target=locked,
            before=before,
            after={
                **snapshot(locked, ["status"]),
                "corrected_by": corrected.public_code,
            },
            reason=reason,
            **audit_actor(actor),
        )
        if was_counting:
            match_changed.send(
                sender=Match,
                match=locked,
                change=MatchChange.EDIT,
                earliest_date=min(locked.played_on, corrected.played_on),
            )
        elif corrected.status == MatchStatus.CONFIRMED:
            match_confirmed.send(sender=Match, match=corrected)
        _send_count_changes(counting)
        return corrected


def expire_unconfirmed_matches(now: datetime | None = None) -> int:
    """Void pending matches older than ``MATCH_CONFIRMATION_EXPIRY_DAYS``.

    Does nothing and returns 0 when the setting is None (the default).
    Each match is voided in its own transaction, with one ``match.expire``
    Audit Event and no actor, and sends ``release`` for each match it no
    longer holds. A match another transaction holds locked is skipped
    until the next run, and a match no longer pending is left alone, so
    running twice is safe. Returns how many matches were voided.
    """
    days: int | None = settings.MATCH_CONFIRMATION_EXPIRY_DAYS
    if days is None:
        return 0
    cutoff = (now or timezone.now()) - timedelta(days=days)
    candidates = list(
        Match.objects.filter(status=MatchStatus.PENDING, created_at__lt=cutoff)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    expired = 0
    for pk in candidates:
        with transaction.atomic():
            locked = (
                Match.objects.select_for_update(skip_locked=True)
                .filter(pk=pk, status=MatchStatus.PENDING, created_at__lt=cutoff)
                .first()
            )
            if locked is None:
                continue
            _void(locked, action=AuditAction.MATCH_EXPIRE, actor=None, reason="")
            expired += 1
    if expired:
        logger.info("Expired %d unconfirmed matches.", expired)
    return expired
