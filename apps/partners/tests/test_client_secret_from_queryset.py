"""A refresh from a queryset that skips the secret cannot launder it.

refresh_from_db(from_queryset=...) with client_secret left out of the
fetched row keeps the in-memory value, which was then treated as the
stored one, so a blank or hash-shaped raw secret skipped the check.
"""

from collections.abc import Callable

import pytest
from django.db.models import QuerySet

from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db

RAW_SECRET = "made-up-client-secret-for-tests-only"


def _only_name() -> QuerySet[PartnerApplication]:
    return PartnerApplication.objects.only("name")


def _defer_secret() -> QuerySet[PartnerApplication]:
    return PartnerApplication.objects.defer("client_secret")


@pytest.mark.parametrize("queryset", [_only_name, _defer_secret])
@pytest.mark.parametrize("secret", [""])
def test_refresh_skipping_the_secret_then_save_is_refused(
    secret: str, queryset: Callable[[], QuerySet[PartnerApplication]]
) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    loaded = PartnerApplication.objects.get(pk=application.pk)
    before = PartnerApplication.objects.values_list("client_secret", flat=True).get(
        pk=application.pk
    )

    loaded.client_secret = secret
    loaded.refresh_from_db(from_queryset=queryset())
    with pytest.raises(ValueError, match="client secret"):
        loaded.save()

    stored = PartnerApplication.objects.values_list("client_secret", flat=True).get(
        pk=application.pk
    )
    assert stored == before


@pytest.mark.parametrize("queryset", [_only_name, _defer_secret])
def test_refresh_skipping_the_secret_then_save_keeps_stored_hash(
    queryset: Callable[[], QuerySet[PartnerApplication]],
) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    loaded = PartnerApplication.objects.get(pk=application.pk)
    before = PartnerApplication.objects.values_list("client_secret", flat=True).get(
        pk=application.pk
    )

    loaded.client_secret = "argon2$argon2id$x"
    loaded.refresh_from_db(from_queryset=queryset())
    loaded.save()

    stored = PartnerApplication.objects.values_list("client_secret", flat=True).get(
        pk=application.pk
    )
    assert stored == before
