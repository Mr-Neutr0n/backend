"""The database refuses an external ID with leading or trailing whitespace.

Raw writes skip the model's stripping, so without this "abc" and "abc "
could both be stored for one application, and "   " would count as an
external ID.
"""

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.matches.models import BestOf, Match, MatchFormat
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("external_id", ["abc ", " abc", "   ", "abc\n"])
def test_untrimmed_external_id_is_refused(external_id: str) -> None:
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Match.objects.create(
            format=MatchFormat.SINGLES,
            played_on=date(2026, 6, 1),
            best_of=BestOf.ONE,
            submitted_by_application=PartnerApplicationFactory.create(),
            external_id=external_id,
        )

    assert "matches_match_external_id_trimmed" in str(error.value)
