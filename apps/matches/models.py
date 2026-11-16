"""Matches: the games two teams played, who played them, and who sent them.

A Match is one entry in the match ledger (CONTEXT.md, Match and Ledger).
The ledger is append-only (CLAUDE.md, hard rule 3): a counted match is
never edited in place or deleted. A correction is a new record that
references the old one. #26 adds the service that makes those changes, with
its Audit Events. Until then nothing in the backend changes a Match after
it is created.

Games and participants use ``PROTECT``, so the ORM refuses to delete a Match
that has either. That is not a full guard: a Match with neither can still be
deleted, ``QuerySet.update`` and raw SQL can still change rows, and nothing
yet stops an edit through ``save()``. #26 owes the full delete and edit
guard.

These models enforce only what a database constraint can: the allowed
values of each choice, one submitter, a ``played_at`` that agrees with its
local date, external IDs unique per Partner Application, at most
``MAX_GAMES`` games, no negative scores, and one Match that is not voided per
fingerprint. Score validation (win by 2, team size per format, games that
decide the match) is ``apps.matches.services.validate_match``, duplicate
detection is ``apps.matches.services.record_match``, and confirmation and
status changes are #26. A possible duplicate is held for review as a
``MatchFlag``, so reviewing it (#40) writes a flag row, never the Match.

``ScoringType`` values equal ``open_engine.ScoringType``'s and
``GameTarget`` values equal the points in the engine's ``ALL_GAME_FORMATS``,
so #44 maps them directly. ``MatchFormat`` holds only the two base values
of ``open_engine.RatingFormat``: #44 derives the doubles categories (mixed,
men's, women's) from the players. ``MatchStatus``, ``BestOf``, and ``Team``
have no engine enum. The match type is not stored: it comes from the
Event's kind, or is self-reported when there is no Event (decision F1 in
#1).
"""

import datetime
from collections.abc import Collection
from datetime import UTC, timedelta
from typing import ClassVar

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import (
    DateField,
    DateTimeField,
    DurationField,
    ExpressionWrapper,
    F,
    Func,
    Q,
    Value,
)
from django.db.models.functions import Cast

from apps.clubs.models import _CleanedTextModel
from apps.events.models import CHOICE_MESSAGES
from apps.public_ids.codes import CodeType

# Shared limits, defined once. Score validation (services.py) imports them.
MAX_GAMES = 5
MIN_UTC_OFFSET_MINUTES = -720
MAX_UTC_OFFSET_MINUTES = 840

# Every character Python's str.isspace() is true for, so the database check
# agrees with the model's str.strip(). Postgres \s depends on the database
# locale and misses some of them. Listed one by one, since a bracket range
# may depend on the collation.
WHITESPACE_CODE_POINTS: tuple[int, ...] = (
    *range(0x0009, 0x000D + 1),
    *range(0x001C, 0x001F + 1),
    0x0020,
    0x0085,
    0x00A0,
    0x1680,
    *range(0x2000, 0x200A + 1),
    0x2028,
    0x2029,
    0x202F,
    0x205F,
    0x3000,
)
_WHITESPACE_CLASS = "[" + "".join(chr(point) for point in WHITESPACE_CODE_POINTS) + "]"

# Messages never include the submitted value (CLAUDE.md, API). Django's
# defaults for these keys do.
_NUMBER_MESSAGES = {"invalid": "Enter a whole number."}
_INTEGER_CHOICE_MESSAGES = {**CHOICE_MESSAGES, **_NUMBER_MESSAGES}
_DATE_MESSAGE = "Enter a valid date in YYYY-MM-DD format."
_DATE_MESSAGES = {"invalid": _DATE_MESSAGE, "invalid_date": _DATE_MESSAGE}
_DATETIME_MESSAGE = "Enter a valid date and time."
_DATETIME_MESSAGES = {
    "invalid": _DATETIME_MESSAGE,
    "invalid_date": _DATE_MESSAGE,
    "invalid_datetime": _DATETIME_MESSAGE,
}
# Django's default names the submitted row id.
_EVENT_MESSAGES = {"invalid": "Choose an existing event."}
_CLUB_MESSAGES = {"invalid": "Choose an existing club."}
_MATCH_MESSAGES = {"invalid": "Choose an existing match."}
_PLAYER_MESSAGES = {"invalid": "Choose an existing player."}
_USER_MESSAGES = {"invalid": "Choose an existing account."}
_APPLICATION_MESSAGES = {"invalid": "Choose an existing partner application."}

_ONE_SUBMITTER = "A match has exactly one submitter: an account or an application."
_EXTERNAL_ID_NEEDS_APPLICATION = (
    "Only a match submitted by a partner application can have an external ID."
)
_EXTERNAL_ID_TAKEN = "This application already submitted a match with this external ID."
_PLAYED_AT_NEEDS_OFFSET = (
    "Give the UTC offset where the match was played with the time played."
)
_OFFSET_NEEDS_PLAYED_AT = (
    "Give the time played with the UTC offset where the match was played."
)
_PLAYED_AT_NAIVE = "Give the time played with its time zone."
_PLAYED_AT_OUT_OF_RANGE = "Enter a time played within the supported dates."
_LOCAL_DATE = "The date played must be the local date of the time played."

# played_at shifted to local time where the match was played, as a date. Postgres keeps a
# timestamptz in UTC and drops its offset, so the offset is stored apart.
# The explicit AT TIME ZONE makes the result independent of the session's
# time zone. (TruncDate's tzinfo cannot be written to a migration.)
_PLAYED_AT_UTC = Func(
    F("played_at"),
    template="(%(expressions)s AT TIME ZONE 'UTC')",
    output_field=DateTimeField(),
)
_LOCAL_PLAYED_ON = Cast(
    _PLAYED_AT_UTC
    + ExpressionWrapper(
        F("played_at_utc_offset") * Value(timedelta(minutes=1)),
        output_field=DurationField(),
    ),
    output_field=DateField(),
)


class _LinkMessagesModel(models.Model):
    """Gives each link's own ``invalid`` message for an id of the wrong type.

    ``ForeignKey.to_python`` converts the id with the target's primary key
    field, whose message repeats the submitted value (CLAUDE.md, API).
    """

    class Meta:
        abstract = True

    def clean_fields(self, exclude: Collection[str] | None = None) -> None:
        try:
            super().clean_fields(exclude=exclude)
        except ValidationError as error:
            errors: dict[str, list[ValidationError]] = {}
            for name, field_errors in error.error_dict.items():
                field = _foreign_key(self, name)
                errors[name] = [
                    ValidationError(field.error_messages["invalid"], code="invalid")
                    if field is not None and item.code == "invalid"
                    else item
                    for item in field_errors
                ]
            raise ValidationError(errors) from None


def _foreign_key(
    instance: models.Model, name: str
) -> models.ForeignKey[models.Model, models.Model] | None:
    try:
        field = instance._meta.get_field(name)
    except FieldDoesNotExist:
        return None
    return field if isinstance(field, models.ForeignKey) else None


class MatchFormat(models.TextChoices):
    """Singles or doubles.

    The values are the two base values of ``open_engine.RatingFormat``. The
    engine's doubles categories (mixed, men's, women's) are not stored here:
    #44 derives them from the players.
    """

    SINGLES = "singles", "Singles"
    DOUBLES = "doubles", "Doubles"


class MatchStatus(models.TextChoices):
    """Where a Match is in confirmation. #26 owns the changes between them."""

    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    DISPUTED = "disputed", "Disputed"
    VOIDED = "voided", "Voided"


class ScoringType(models.TextChoices):
    """How points are scored. The values are ``open_engine.ScoringType``'s."""

    SIDE_OUT = "side_out", "Side-out"
    RALLY = "rally", "Rally"


class BestOf(models.IntegerChoices):
    """How many games a Match is played to (decision F15 in #1)."""

    ONE = 1, "Best of 1"
    THREE = 3, "Best of 3"
    FIVE = 5, "Best of 5"


class GameTarget(models.IntegerChoices):
    """The points a game is played to (decision F15 in #1).

    The values are the points in the engine's ``ALL_GAME_FORMATS``.
    """

    ELEVEN = 11, "11 points"
    FIFTEEN = 15, "15 points"
    TWENTY_ONE = 21, "21 points"


class Team(models.TextChoices):
    """One side of a Match."""

    A = "A", "Team A"
    B = "B", "Team B"


class Match(_LinkMessagesModel, _CleanedTextModel):
    """One match in the ledger (CONTEXT.md, Match).

    Exactly one of ``submitted_by_user`` and ``submitted_by_application`` is
    set. ``external_id`` is the submitting application's own id for the
    match, so only an application's match has one.

    ``played_at`` and ``played_at_utc_offset`` are both set or both empty.
    The offset is minutes east of UTC where the match was played, and
    ``played_at`` shifted by it falls on ``played_on``.

    ``location`` is the place's name, such as a court or park. It is never a
    street address or an exact location (ADR 0009).
    """

    public_code_type = CodeType.MATCH
    TEXT_FIELDS: ClassVar[tuple[str, ...]] = (
        "external_id",
        "location",
        "event_label",
        "bracket_label",
    )

    format = models.CharField(
        max_length=10, choices=MatchFormat, error_messages=CHOICE_MESSAGES
    )
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="matches",
        error_messages=_EVENT_MESSAGES,
    )
    club = models.ForeignKey(
        "clubs.Club",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="matches",
        error_messages=_CLUB_MESSAGES,
    )
    played_on = models.DateField(error_messages=_DATE_MESSAGES)
    played_at = models.DateTimeField(
        null=True, blank=True, error_messages=_DATETIME_MESSAGES
    )
    played_at_utc_offset = models.SmallIntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(MIN_UTC_OFFSET_MINUTES),
            MaxValueValidator(MAX_UTC_OFFSET_MINUTES),
        ],
        error_messages=_NUMBER_MESSAGES,
        help_text="Minutes east of UTC where the match was played",
    )
    sequence = models.PositiveIntegerField(default=0, error_messages=_NUMBER_MESSAGES)
    status = models.CharField(
        max_length=10,
        choices=MatchStatus,
        default=MatchStatus.PENDING,
        error_messages=CHOICE_MESSAGES,
    )
    best_of = models.PositiveSmallIntegerField(
        choices=BestOf, error_messages=_INTEGER_CHOICE_MESSAGES
    )
    game_target = models.PositiveSmallIntegerField(
        choices=GameTarget,
        default=GameTarget.ELEVEN,
        error_messages=_INTEGER_CHOICE_MESSAGES,
    )
    scoring_type = models.CharField(
        max_length=10,
        choices=ScoringType,
        default=ScoringType.SIDE_OUT,
        error_messages=CHOICE_MESSAGES,
    )
    submitted_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submitted_matches",
        error_messages=_USER_MESSAGES,
    )
    submitted_by_application = models.ForeignKey(
        settings.OAUTH2_PROVIDER_APPLICATION_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submitted_matches",
        error_messages=_APPLICATION_MESSAGES,
    )
    external_id = models.CharField(max_length=128, blank=True, default="")
    location = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="The place's name, such as a court or park. Never a street address.",
    )
    event_label = models.CharField(max_length=200, blank=True, default="")
    bracket_label = models.CharField(max_length=200, blank=True, default="")
    fingerprint = models.CharField(
        max_length=64,
        blank=True,
        default="",
        editable=False,
        help_text=(
            "SHA-256 hex digest of the teams, date played, and game scores, "
            "set by record_match()"
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "matches"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=(
                    Q(submitted_by_user__isnull=False)
                    & Q(submitted_by_application__isnull=True)
                )
                | (
                    Q(submitted_by_user__isnull=True)
                    & Q(submitted_by_application__isnull=False)
                ),
                name="matches_match_one_submitter",
            ),
            models.CheckConstraint(
                condition=Q(format__in=MatchFormat.values),
                name="matches_match_format_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=MatchStatus.values),
                name="matches_match_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(scoring_type__in=ScoringType.values),
                name="matches_match_scoring_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(best_of__in=BestOf.values),
                name="matches_match_best_of_valid",
            ),
            models.CheckConstraint(
                condition=Q(game_target__in=GameTarget.values),
                name="matches_match_game_target_valid",
            ),
            models.CheckConstraint(
                condition=Q(played_at__isnull=True, played_at_utc_offset__isnull=True)
                | Q(played_at__isnull=False, played_at_utc_offset__isnull=False),
                name="matches_match_played_at_pair",
            ),
            models.CheckConstraint(
                condition=Q(
                    played_at_utc_offset__gte=MIN_UTC_OFFSET_MINUTES,
                    played_at_utc_offset__lte=MAX_UTC_OFFSET_MINUTES,
                ),
                name="matches_match_played_at_utc_offset_range",
            ),
            models.CheckConstraint(
                condition=Q(played_on=_LOCAL_PLAYED_ON),
                name="matches_match_played_at_local_date",
            ),
            models.CheckConstraint(
                condition=Q(external_id="") | Q(submitted_by_application__isnull=False),
                name="matches_match_external_id_needs_application",
            ),
            models.CheckConstraint(
                # Raw writes skip the model's stripping.
                condition=~Q(
                    external_id__regex=f"^{_WHITESPACE_CLASS}|{_WHITESPACE_CLASS}$"
                ),
                name="matches_match_external_id_trimmed",
            ),
            models.UniqueConstraint(
                fields=("submitted_by_application", "external_id"),
                condition=~Q(external_id=""),
                name="matches_match_external_id_unique_per_application",
                violation_error_message=_EXTERNAL_ID_TAKEN,
            ),
            models.UniqueConstraint(
                fields=("fingerprint",),
                condition=~Q(fingerprint="") & ~Q(status=MatchStatus.VOIDED),
                name="matches_match_fingerprint_unique_unless_voided",
                violation_error_message="This match was already submitted.",
            ),
        ]

    def __str__(self) -> str:
        # The OPEN Code, never a name, for one rule with Club and Event.
        return self.public_code

    def clean(self) -> None:
        # Django runs clean() even when a field failed, so a value may still
        # be the raw input here: check its type before using it.
        errors: dict[str, str] = {}
        has_user = self.submitted_by_user_id is not None
        has_application = self.submitted_by_application_id is not None
        if has_user == has_application:
            errors["submitted_by_user"] = _ONE_SUBMITTER
            errors["submitted_by_application"] = _ONE_SUBMITTER
        if self.external_id and not has_application:
            errors["external_id"] = _EXTERNAL_ID_NEEDS_APPLICATION

        played_at, offset = self.played_at, self.played_at_utc_offset
        if played_at is not None and offset is None:
            errors["played_at_utc_offset"] = _PLAYED_AT_NEEDS_OFFSET
        elif played_at is None and offset is not None:
            errors["played_at"] = _OFFSET_NEEDS_PLAYED_AT
        elif isinstance(played_at, datetime.datetime) and played_at.utcoffset() is None:
            errors["played_at"] = _PLAYED_AT_NAIVE
        elif (
            isinstance(played_at, datetime.datetime)
            and isinstance(offset, int)
            and MIN_UTC_OFFSET_MINUTES <= offset <= MAX_UTC_OFFSET_MINUTES
            and isinstance(self.played_on, datetime.date)
            and not isinstance(self.played_on, datetime.datetime)
        ):
            try:
                local = played_at.astimezone(UTC) + timedelta(minutes=offset)
            except OverflowError:
                errors["played_at"] = _PLAYED_AT_OUT_OF_RANGE
            else:
                if local.date() != self.played_on:
                    errors["played_on"] = _LOCAL_DATE
        if errors:
            raise ValidationError(errors)


class MatchParticipant(_LinkMessagesModel):
    """A Player on one team of a Match. A Player plays once per Match."""

    match = models.ForeignKey(
        Match,
        on_delete=models.PROTECT,
        related_name="participants",
        error_messages=_MATCH_MESSAGES,
    )
    player = models.ForeignKey(
        "players.Player",
        on_delete=models.PROTECT,
        related_name="match_participations",
        error_messages=_PLAYER_MESSAGES,
    )
    team = models.CharField(max_length=1, choices=Team, error_messages=CHOICE_MESSAGES)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(team__in=Team.values),
                name="matches_matchparticipant_team_valid",
            ),
            models.UniqueConstraint(
                fields=("match", "player"),
                name="matches_matchparticipant_player_once_per_match",
                violation_error_message="This player is already in this match.",
            ),
        ]

    def __str__(self) -> str:
        # The match code and team, never the Player's name.
        return f"{self.match.public_code} team {self.team}"


class Game(_LinkMessagesModel):
    """One game of a Match, numbered from 1. Scores are never negative."""

    match = models.ForeignKey(
        Match,
        on_delete=models.PROTECT,
        related_name="games",
        error_messages=_MATCH_MESSAGES,
    )
    game_number = models.PositiveSmallIntegerField(error_messages=_NUMBER_MESSAGES)
    team_a_score = models.PositiveSmallIntegerField(error_messages=_NUMBER_MESSAGES)
    team_b_score = models.PositiveSmallIntegerField(error_messages=_NUMBER_MESSAGES)

    class Meta:
        ordering = ("match", "game_number")
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(game_number__gte=1, game_number__lte=MAX_GAMES),
                name="matches_game_number_range",
            ),
            models.UniqueConstraint(
                fields=("match", "game_number"),
                name="matches_game_number_once_per_match",
                violation_error_message="This match already has a game with this number.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.match.public_code} game {self.game_number}"


class FlagReason(models.TextChoices):
    """Why a Match was flagged for review."""

    POSSIBLE_DUPLICATE = "possible_duplicate", "Possible duplicate"


class MatchFlag(_LinkMessagesModel):
    """A reason to hold a Match for Organizer review (CONTEXT.md, Flagged Match).

    ``record_match()`` creates a ``possible_duplicate`` flag for each
    earlier Match that is not voided with the same teams and date but other scores,
    with ``duplicate_of`` set to it. A flag is a row of its own, so
    reviewing one never edits the Match in the ledger.

    #26 and #44 must not count a Match that has an open flag. #40 adds the
    review actions and any resolution fields.
    """

    match = models.ForeignKey(
        Match,
        on_delete=models.PROTECT,
        related_name="flags",
        error_messages=_MATCH_MESSAGES,
    )
    reason = models.CharField(
        max_length=30, choices=FlagReason, error_messages=CHOICE_MESSAGES
    )
    duplicate_of = models.ForeignKey(
        Match,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="duplicate_flags",
        error_messages=_MATCH_MESSAGES,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(reason__in=FlagReason.values),
                name="matches_matchflag_reason_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    reason=FlagReason.POSSIBLE_DUPLICATE, duplicate_of__isnull=False
                )
                | (
                    ~Q(reason=FlagReason.POSSIBLE_DUPLICATE)
                    & Q(duplicate_of__isnull=True)
                ),
                name="matches_matchflag_duplicate_of_matches_reason",
                violation_error_message=(
                    "A possible duplicate flag names the match it may duplicate."
                ),
            ),
            models.CheckConstraint(
                condition=~Q(duplicate_of=F("match")),
                name="matches_matchflag_not_self",
                violation_error_message="A match cannot duplicate itself.",
            ),
            models.UniqueConstraint(
                fields=("match", "duplicate_of"),
                name="matches_matchflag_once_per_pair",
                violation_error_message=(
                    "This match is already flagged as a duplicate of that match."
                ),
            ),
        ]

    def __str__(self) -> str:
        # The match code and reason, never a name.
        return f"{self.match.public_code} flag {self.reason}"
