"""MATCH_CONFIRMATION_EXPIRY_DAYS has an upper bound (review finding H, #26).

Without one, a huge value passed the settings check and then made every
expiry run fail with OverflowError, and a value of thousands of digits
failed with a bare ValueError. At most 36500 days is accepted.
"""

import json

import pytest

from config.tests.test_settings import LOCAL_DEBUG, _run

NAME = "MATCH_CONFIRMATION_EXPIRY_DAYS"

PRINT_EXPIRY = """
import json
import django
from django.conf import settings
django.setup()
print(json.dumps(settings.MATCH_CONFIRMATION_EXPIRY_DAYS))
"""


def test_the_largest_value_is_accepted() -> None:
    result = _run(["-c", PRINT_EXPIRY], {**LOCAL_DEBUG, NAME: "36500"})

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == 36500


@pytest.mark.parametrize("value", ["36501", "99999", "1000000", "9" * 5000])
def test_a_value_above_the_bound_stops_startup(value: str) -> None:
    result = _run(["manage.py", "check"], {**LOCAL_DEBUG, NAME: value})

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert NAME in result.stderr
    assert "36500" in result.stderr
    assert value not in result.stderr
    assert "ValueError" not in result.stderr
