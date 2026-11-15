"""A secret loaded after the fact (deferred or refreshed) still saves.

The stored value was recorded only in from_db, so a secret loaded later
by refresh_from_db (a deferred field read, or an explicit refresh)
looked new, and its stored hash was refused as hash-shaped.
"""

import pytest

from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db

RAW_SECRET = "made-up-client-secret-for-tests-only"


def test_deferred_secret_read_then_save() -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    partial = PartnerApplication.objects.only("pk", "name").get(pk=application.pk)

    assert partial.client_secret  # loads the deferred field
    partial.name = "Made-up Renamed App"
    partial.full_clean()
    partial.save()

    assert PartnerApplication.objects.get(pk=application.pk).name == (
        "Made-up Renamed App"
    )


def test_refresh_after_another_change_then_save() -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    mine = PartnerApplication.objects.get(pk=application.pk)
    other = PartnerApplication.objects.get(pk=application.pk)
    other.client_secret = "made-up-rotated-secret-for-tests"
    other.save()

    mine.refresh_from_db()
    mine.name = "Made-up Renamed App"
    mine.full_clean()
    mine.save()

    stored = PartnerApplication.objects.get(pk=application.pk)
    assert stored.name == "Made-up Renamed App"
    assert stored.client_secret == other.client_secret


def test_refresh_of_other_fields_keeps_the_marker() -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    loaded = PartnerApplication.objects.get(pk=application.pk)

    loaded.client_secret = ""
    loaded.refresh_from_db(fields=["name"])

    with pytest.raises(ValueError, match="client secret"):
        loaded.save()
