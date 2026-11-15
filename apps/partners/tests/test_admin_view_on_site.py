"""The admin offers no "View on site" for a Partner Application.

DOT's get_absolute_url() reverses its application detail view, which
OPEN does not mount, so following it raised NoReverseMatch (a 500).
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser_client(client: Client) -> Client:
    client.force_login(UserFactory.create(is_staff=True, is_superuser=True))
    return client


def test_change_page_has_no_view_on_site_link(superuser_client: Client) -> None:
    application = PartnerApplicationFactory.create()

    response = superuser_client.get(
        reverse("admin:partners_partnerapplication_change", args=[application.pk])
    )

    assert response.status_code == 200
    assert b"viewsitelink" not in response.content
    assert response.context["has_absolute_url"] is False


def test_admin_shortcut_url_is_not_a_server_error(superuser_client: Client) -> None:
    application = PartnerApplicationFactory.create()
    content_type = ContentType.objects.get_for_model(PartnerApplication)
    superuser_client.raise_request_exception = False

    response = superuser_client.get(
        reverse("admin:view_on_site", args=[content_type.pk, application.pk])
    )

    assert response.status_code == 404
