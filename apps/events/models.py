"""Events: tournaments, leagues, and verified rec sessions an Organizer runs.

An Event groups the matches played under one Organizer, optionally at a
Club, over a span of dates. Its ``kind`` is the match type its matches
count as. Self-reported matches have no Event (decision F1 in #1).

The ``weight`` is stored and validated but not yet applied to ratings. The
engine weights a match only by its match type today and takes no
per-event weight, so applying it here would be rating math outside the
engine (CLAUDE.md, hard rule 2). An engine issue asks whether the engine
should accept it.

#125 adds the Event API.
"""

import datetime
from collections.abc import Collection
from decimal import Decimal
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.clubs.models import _CleanedTextModel
from apps.public_ids.codes import CodeType

MIN_WEIGHT = Decimal("0.01")
MAX_WEIGHT = Decimal("1.00")
DEFAULT_WEIGHT = Decimal("1.00")

# Messages never include the submitted value (CLAUDE.md, API). Django's
# defaults for these keys do.
CHOICE_MESSAGES = {"invalid_choice": "Choose one of the listed options."}
_DATE_MESSAGE = "Enter a valid date in YYYY-MM-DD format."
_DATE_MESSAGES = {"invalid": _DATE_MESSAGE, "invalid_date": _DATE_MESSAGE}
_NUMBER_MESSAGES = {"invalid": "Enter a number."}
_DATES_ORDER = "The end date cannot be before the start date."
_DATE_FIELDS = frozenset({"start_date", "end_date"})
# Django's default names the submitted row id.
_ORGANIZER_MESSAGES = {"invalid": "Choose an existing organizer."}
_CLUB_MESSAGES = {"invalid": "Choose an existing club."}


class EventKind(models.TextChoices):
    """The match type an Event's matches count as.

    The values are the engine's ``open_engine.MatchType`` values.
    ``self_reported`` is left out: self-reported matches have no Event
    (decision F1 in #1). Never add a value the engine lacks.
    """

    TOURNAMENT = "tournament", "Tournament"
    LEAGUE = "league", "League"
    REC_VERIFIED = "rec_verified", "Verified rec play"


class Event(_CleanedTextModel):
    """A tournament, league, or verified rec session (CONTEXT.md, Event)."""

    public_code_type = CodeType.EVENT
    TEXT_FIELDS: ClassVar[tuple[str, ...]] = ("name",)

    name = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=20, choices=EventKind, error_messages=CHOICE_MESSAGES
    )
    organizer = models.ForeignKey(
        "clubs.Organizer",
        on_delete=models.PROTECT,
        related_name="events",
        error_messages=_ORGANIZER_MESSAGES,
    )
    club = models.ForeignKey(
        "clubs.Club",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="events",
        error_messages=_CLUB_MESSAGES,
    )
    start_date = models.DateField(error_messages=_DATE_MESSAGES)
    end_date = models.DateField(error_messages=_DATE_MESSAGES)
    weight = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=DEFAULT_WEIGHT,
        validators=[MinValueValidator(MIN_WEIGHT), MaxValueValidator(MAX_WEIGHT)],
        error_messages=_NUMBER_MESSAGES,
        help_text=(
            "From 0.01 to 1.00. Stored for later use: not yet applied to ratings."
        ),
    )

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                # Refuses "" and whitespace only.
                condition=~Q(name__regex=r"^\s*$"),
                name="events_event_name_not_empty",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=EventKind.values),
                name="events_event_kind_valid",
            ),
            models.CheckConstraint(
                condition=Q(weight__gt=0, weight__lte=MAX_WEIGHT),
                name="events_event_weight_range",
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="events_event_dates_ordered",
            ),
        ]

    def __str__(self) -> str:
        # The OPEN Code, never the name, for one rule with Club and Organizer.
        return self.public_code

    def clean_fields(self, exclude: Collection[str] | None = None) -> None:
        """Validate the fields, noting each date that was not checked.

        A date that failed or was excluded is not a value to compare: a
        form leaves a field that failed at its stored value, and Django
        still runs ``clean()``.
        """
        self._unchecked_dates = _DATE_FIELDS & set(exclude or ())
        try:
            super().clean_fields(exclude=exclude)
        except ValidationError as error:
            self._unchecked_dates |= _DATE_FIELDS & set(error.message_dict)
            raise

    def clean(self) -> None:
        if getattr(self, "_unchecked_dates", None):
            return
        # Called without clean_fields(), a date may still be raw input.
        start, end = self.start_date, self.end_date
        if (
            isinstance(start, datetime.date)
            and isinstance(end, datetime.date)
            and end < start
        ):
            raise ValidationError({"end_date": _DATES_ORDER})
