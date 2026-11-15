"""Players and their privacy settings. See ADR 0002 and ADR 0009.

Create a Player through ``apps.players.services.create_player``, which
also creates its PlayerPrivacy row. Only the player changes these fields
and settings, through the services in that module.
"""

from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.public_ids.codes import CodeType
from apps.public_ids.models import PublicCodeModel

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

# Messages never include the submitted value (CLAUDE.md, API). Django's
# defaults for these keys do.
_CHOICE_MESSAGES = {"invalid_choice": "Choose one of the listed options."}
_INTEGER_MESSAGES = {"invalid": "Enter a whole number."}

EARLIEST_BIRTH_YEAR = 1900

# One setting per profile detail other than the display name and current
# Ratings, which have none (ADR 0002).
PRIVACY_SETTINGS = (
    "city_region_visibility",
    "match_history_visibility",
    "rating_history_visibility",
    "stats_visibility",
    "home_club_visibility",
)


class Visibility(models.TextChoices):
    """Who may see a profile detail. ``PRIVATE`` is the most restrictive."""

    SIGNED_IN = "signed_in", "Signed-in players"
    PRIVATE = "private", "Only me"


class GenderDivision(models.TextChoices):
    """The gender division a Player enters. An empty value means none."""

    MENS = "mens", "Men's"
    WOMENS = "womens", "Women's"


class Player(PublicCodeModel):
    """A person who plays matches and has ratings (CONTEXT.md, Player).

    Every Player belongs to one Account, and an Account has at most one
    Player (ADR 0002). The fields are the ones ADR 0009 allows, and no
    others: never a full birthdate or a raw gender.
    """

    public_code_type = CodeType.PLAYER

    # PROTECT: deleting an Account keeps its Player (ADR 0002). #116
    # decides how.
    account = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="player"
    )
    display_name = models.CharField(max_length=64)
    legal_name = models.CharField(max_length=200, blank=True)
    birth_year = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(EARLIEST_BIRTH_YEAR)],
        error_messages=_INTEGER_MESSAGES,
    )
    # Never the day (ADR 0009).
    birth_month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        error_messages=_INTEGER_MESSAGES,
    )
    gender_division = models.CharField(
        max_length=8,
        choices=GenderDivision,
        blank=True,
        error_messages=_CHOICE_MESSAGES,
    )
    city = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=~Q(display_name=""),
                name="players_player_display_name_not_empty",
            ),
            models.CheckConstraint(
                condition=Q(birth_month__gte=1, birth_month__lte=12),
                name="players_player_birth_month_range",
            ),
            models.CheckConstraint(
                condition=Q(birth_year__gte=EARLIEST_BIRTH_YEAR),
                name="players_player_birth_year_min",
            ),
            models.CheckConstraint(
                condition=Q(gender_division__in=["", *GenderDivision.values]),
                name="players_player_gender_division_valid",
            ),
        ]

    def __str__(self) -> str:
        # The OPEN Code, never a name (ADR 0009).
        return self.public_code

    def clean(self) -> None:
        for name in ("display_name", "legal_name", "city", "region"):
            value = getattr(self, name)
            if isinstance(value, str):
                setattr(self, name, value.strip())
        errors: dict[str, str] = {}
        if not self.display_name:
            errors["display_name"] = "Enter a display name."
        if self._birth_month_is_in_the_future():
            errors["birth_month"] = "The birth year and month cannot be in the future."
        if errors:
            raise ValidationError(errors)

    def _birth_month_is_in_the_future(self) -> bool:
        year, month = self.birth_year, self.birth_month
        if not isinstance(year, int) or not isinstance(month, int):
            # Field validation reports a missing or malformed value.
            return False
        today = timezone.localdate()
        return (year, month) > (today.year, today.month)


class PlayerPrivacy(models.Model):
    """Who may see each of a Player's other profile details.

    There is no setting for the display name or current Ratings: once
    Ratings are published, every signed-in Account sees them (ADR 0002).
    """

    SETTINGS: ClassVar[tuple[str, ...]] = PRIVACY_SETTINGS

    player = models.OneToOneField(
        Player, on_delete=models.CASCADE, primary_key=True, related_name="privacy"
    )
    city_region_visibility = models.CharField(
        max_length=16,
        choices=Visibility,
        default=Visibility.SIGNED_IN,
        error_messages=_CHOICE_MESSAGES,
    )
    match_history_visibility = models.CharField(
        max_length=16,
        choices=Visibility,
        default=Visibility.SIGNED_IN,
        error_messages=_CHOICE_MESSAGES,
    )
    rating_history_visibility = models.CharField(
        max_length=16,
        choices=Visibility,
        default=Visibility.SIGNED_IN,
        error_messages=_CHOICE_MESSAGES,
    )
    stats_visibility = models.CharField(
        max_length=16,
        choices=Visibility,
        default=Visibility.SIGNED_IN,
        error_messages=_CHOICE_MESSAGES,
    )
    home_club_visibility = models.CharField(
        max_length=16,
        choices=Visibility,
        default=Visibility.SIGNED_IN,
        error_messages=_CHOICE_MESSAGES,
    )

    class Meta:
        verbose_name = "player privacy settings"
        verbose_name_plural = "player privacy settings"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(**{f"{name}__in": Visibility.values}),
                name=f"players_playerprivacy_{name}_valid",
            )
            for name in PRIVACY_SETTINGS
        ]

    def __str__(self) -> str:
        # The OPEN Code, never a name (ADR 0009).
        return self.player.public_code

    def visible_to(self, setting: str, viewer: "_User | AnonymousUser | None") -> bool:
        """True when ``viewer`` may see the detail ``setting`` covers.

        Nobody signed out or inactive sees anything. The player's own
        Account always does. Another Account does only at ``SIGNED_IN``.
        """
        if setting not in self.SETTINGS:
            raise ValueError(f"{setting} is not a privacy setting.")
        if viewer is None or not viewer.is_authenticated or not viewer.is_active:
            return False
        if viewer.pk == self.player.account_id:
            return True
        return bool(getattr(self, setting) == Visibility.SIGNED_IN)
