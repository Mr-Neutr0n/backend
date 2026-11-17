"""Helpers for tests of allauth's headless API (issue #30).

Made-up data only, never real player data. Requests go through Django's
test client and the whole middleware stack.
"""

import re
from typing import Any
from urllib.parse import unquote

import pytest
from django.conf import settings
from django.core import mail
from django.http import HttpResponseBase
from django.test import Client, TestCase
from django.test.client import ClientHandler

APP = "/_allauth/app/v1"
BROWSER = "/_allauth/browser/v1"
# The web app origin the email links use, whatever the environment sets.
FRONTEND_URL: str = settings.FRONTEND_URL
PASSWORD = "made-up-Passw0rd-for-tests"
NEW_PASSWORD = "another-made-up-Passw0rd-2"

VERIFY_PREFIX = f"{FRONTEND_URL}/account/verify-email/"
RESET_PREFIX = f"{FRONTEND_URL}/account/password/reset/key/"


def post(client: Client, path: str, data: dict[str, Any], **headers: str) -> Any:
    """POST a JSON body and return the response."""
    return client.post(path, data, content_type="application/json", headers=headers)


def app_headers(token: str | None) -> dict[str, str]:
    """The app client's session token header, when there is a token."""
    return {"X-Session-Token": token} if token else {}


def signup(client: Client, base: str, email: str, password: str = PASSWORD) -> Any:
    return post(client, f"{base}/auth/signup", {"email": email, "password": password})


def login(
    client: Client,
    base: str,
    email: str,
    password: str = PASSWORD,
    **headers: str,
) -> Any:
    return post(
        client,
        f"{base}/auth/login",
        {"email": email, "password": password},
        **headers,
    )


def link_in_last_mail(prefix: str) -> str:
    """The one link in the last email that starts with prefix."""
    body = str(mail.outbox[-1].body)
    links = re.findall(re.escape(prefix) + r"\S+", body)
    assert len(links) == 1, body
    return str(links[0])


def key_from_link(link: str, prefix: str) -> str:
    """The key in a link's path, decoded as the web app's router would."""
    return unquote(link.removeprefix(prefix))


def verify_from_last_mail(client: Client, base: str, **headers: str) -> Any:
    """Verify the address with the key from the last email's link."""
    key = key_from_link(link_in_last_mail(VERIFY_PREFIX), VERIFY_PREFIX)
    return post(client, f"{base}/auth/email/verify", {"key": key}, **headers)


def browser_client() -> Client:
    """A browser client that enforces CSRF, holding a CSRF cookie."""
    client = Client(enforce_csrf_checks=True)
    response = client.get(f"{BROWSER}/config")
    assert response.status_code == 200
    return client


def csrf_header(client: Client) -> dict[str, str]:
    return {"X-CSRFToken": client.cookies["csrftoken"].value}


def run_on_commit_after_each_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the on_commit callbacks a test client request registers.

    In production a request's transactions commit before the response,
    and the queued email task then sends the message (ADR 0016). A test
    runs inside one transaction that never commits, so this runs each
    request's callbacks when it returns, as a commit would. Mail then
    reaches ``mail.outbox`` when the response comes back, as before.
    """
    original = ClientHandler.__call__

    def call(self: ClientHandler, environ: dict[str, Any]) -> HttpResponseBase:
        with TestCase.captureOnCommitCallbacks(execute=True):
            response: HttpResponseBase = original(self, environ)
        return response

    monkeypatch.setattr(ClientHandler, "__call__", call)
