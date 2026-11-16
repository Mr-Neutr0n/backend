"""The partners test helpers make the records they promise."""

import pytest

from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import (
    PartnerApplicationFactory,
    approved_application,
)

pytestmark = pytest.mark.django_db


def test_application_factory_makes_an_unapproved_application() -> None:
    application = PartnerApplicationFactory.create()

    assert not PartnerApplication.objects.get(pk=application.pk).is_approved


def test_approved_application_is_stored_approved() -> None:
    application = approved_application()

    stored = PartnerApplication.objects.get(pk=application.pk)
    assert stored.is_approved
    assert stored.approved_by_id is not None
