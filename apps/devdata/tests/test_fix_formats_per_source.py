"""Every seeded Event and Club gets both singles and doubles Matches (#41).

The seed once chose the source and the format with the same index, so
with four sources and two formats each source got only one format.
"""

import pytest
from django.core.management import call_command
from pytest_django.fixtures import Settings

from apps.clubs.models import Club
from apps.events.models import Event
from apps.matches.models import Match, MatchFormat

BOTH_FORMATS = {MatchFormat.SINGLES, MatchFormat.DOUBLES}


@pytest.mark.django_db
def test_every_event_and_club_has_both_formats(settings: Settings) -> None:
    settings.DEBUG = True

    call_command("seed_dev_data", "--players", "8")

    for event in Event.objects.all():
        formats = set(
            Match.objects.filter(event=event).values_list("format", flat=True)
        )
        assert formats == BOTH_FORMATS, event.public_code
    for club in Club.objects.all():
        formats = set(Match.objects.filter(club=club).values_list("format", flat=True))
        assert formats == BOTH_FORMATS, club.public_code
