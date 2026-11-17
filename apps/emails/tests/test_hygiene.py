"""The email hygiene checks catch links outside the web app (issue #36).

A check that never fails proves nothing, so each bad link here must
fail it and a good one must pass.
"""

from pathlib import Path

import pytest
from django.conf import settings

from apps.emails.tests.hygiene import (
    assert_clean_template,
    assert_links_only_to_the_web_app,
)

FRONTEND_URL: str = settings.FRONTEND_URL


def test_a_link_into_the_web_app_passes() -> None:
    assert_links_only_to_the_web_app(
        f'<a href="{FRONTEND_URL}/matches/M-MADE?a=1&amp;b=2">Open</a>'
    )


@pytest.mark.parametrize(
    "anchor",
    [
        '<a href="/account/signup">x</a>',
        '<a href="//made-up.example.org/x">x</a>',
        '<a href="mailto:someone@example.org">x</a>',
        "<a href='https://made-up.example.org/x'>x</a>",
        '<a href="">x</a>',
        "<a href=https://made-up.example.org/x>x</a>",
        f'<a href="{FRONTEND_URL}.made-up.example.org/x">x</a>',
    ],
)
def test_a_link_outside_the_web_app_fails(anchor: str) -> None:
    with pytest.raises(AssertionError):
        assert_links_only_to_the_web_app(anchor)


def test_a_template_href_must_be_one_variable(tmp_path: Path) -> None:
    good = tmp_path / "good.html"
    good.write_text('<a href="{{ match.url }}">x</a>\n')
    assert_clean_template(good)

    for value in ("/account/signup", "{{ url }}/extra", "mailto:{{ email }}"):
        bad = tmp_path / "bad.html"
        bad.write_text(f'<a href="{value}">x</a>\n')
        with pytest.raises(AssertionError):
            assert_clean_template(bad)
