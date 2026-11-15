"""A secret that only parses as a hash is refused, never stored as is.

These values pass a hasher's decode(), so ClientSecretField stores them
unhashed. DOT's check_password then raises on them and falls back to a
plain comparison, so the stored string itself authenticates.
"""

import pytest

from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db

DECODABLE = [
    "pbkdf2_sha256$1$$x",
    "pbkdf2_sha1$1$$x",
    "pbkdf2_sha256$-1$salt$x",
    "scrypt$3$salt$8$1$x",
    "scrypt$16384$$8$5$x",
    "bcrypt_sha256$$2b$12$abcdefghijklmnopqrstuvABCDEFGHIJKLMNOPQRSTUVWXYZ01234",
]


@pytest.mark.parametrize("secret", DECODABLE)
def test_create_with_decodable_hash_is_refused(secret: str) -> None:
    with pytest.raises(ValueError, match="client secret"):
        PartnerApplicationFactory.create(client_secret=secret)

    assert PartnerApplication.objects.count() == 0
