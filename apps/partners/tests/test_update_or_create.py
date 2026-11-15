"""update_or_create on an existing application keeps its stored hash.

Django adds every field that overrides pre_save, client_secret
included, to the update_fields of update_or_create, so the loaded hash
was checked as a new secret and refused.
"""

import pytest
from asgiref.sync import async_to_sync

from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db

RAW_SECRET = "made-up-client-secret-for-tests-only"


def _stored(pk: int) -> str:
    return PartnerApplication.objects.values_list("client_secret", flat=True).get(pk=pk)


def test_update_or_create_renames_and_keeps_the_hash() -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    before = _stored(application.pk)

    _, created = PartnerApplication.objects.update_or_create(
        pk=application.pk, defaults={"name": "Made-up Renamed App"}
    )

    assert created is False
    assert PartnerApplication.objects.get(pk=application.pk).name == (
        "Made-up Renamed App"
    )
    assert _stored(application.pk) == before


def test_aupdate_or_create_renames_and_keeps_the_hash() -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    before = _stored(application.pk)

    async def rename() -> tuple[PartnerApplication, bool]:
        return await PartnerApplication.objects.aupdate_or_create(
            pk=application.pk, defaults={"name": "Made-up Async Renamed App"}
        )

    _, created = async_to_sync(rename)()

    assert created is False
    assert PartnerApplication.objects.get(pk=application.pk).name == (
        "Made-up Async Renamed App"
    )
    assert _stored(application.pk) == before
