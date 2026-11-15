"""HS256 on the admin add form is a form error, not a server error.

HS256 needs an unhashed secret, which OPEN never stores. DOT's form
re-keys the model's error, since the form has no hash_client_secret.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.partners.models import PartnerApplication

pytestmark = pytest.mark.django_db


def test_hs256_is_a_form_error(client: Client) -> None:
    client.force_login(UserFactory.create(is_staff=True, is_superuser=True))
    client.raise_request_exception = False

    response = client.post(
        reverse("admin:partners_partnerapplication_add"),
        {
            "client_id": "made-up-hs256-client-id",
            "user": "",
            "organizer": "",
            "redirect_uris": "",
            "post_logout_redirect_uris": "",
            "client_type": PartnerApplication.CLIENT_CONFIDENTIAL,
            "authorization_grant_type": PartnerApplication.GRANT_CLIENT_CREDENTIALS,
            "client_secret": "made-up-client-secret-for-tests-only",
            "name": "Made-up HS256 App",
            "algorithm": PartnerApplication.HS256_ALGORITHM,
            "allowed_origins": "",
            "is_sandbox": "on",
        },
    )

    assert response.status_code == 200
    assert response.context["adminform"].form.errors
    assert PartnerApplication.objects.count() == 0
