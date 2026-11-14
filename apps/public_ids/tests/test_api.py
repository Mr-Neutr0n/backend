"""A public code path parameter resolves loose input and hides bad input as 404."""

import uuid
from typing import Annotated, Any

import pytest
from django.http import HttpRequest
from ninja import Schema
from ninja.testing import TestClient

from apps.public_ids import codes
from apps.public_ids.api import PublicCodePath, get_by_public_code
from apps.public_ids.codes import CodeType
from apps.public_ids.models import PublicCodeModel
from config.api import OpenNinjaAPI

pytestmark = pytest.mark.django_db

NOT_FOUND = {"code": "not_found", "message": "Not found.", "errors": []}


class _ThingOut(Schema):
    public_code: str
    label: str


def _api(thing_model: type[PublicCodeModel]) -> OpenNinjaAPI:
    api = OpenNinjaAPI(urls_namespace=f"test-{uuid.uuid4().hex}")

    @api.get("/things/{code}", response=_ThingOut, operation_id="get_thing")
    def get_thing(
        request: HttpRequest,
        code: Annotated[str, PublicCodePath(CodeType.PLAYER)],
    ) -> PublicCodeModel:
        return get_by_public_code(thing_model._default_manager.all(), code)

    return api


@pytest.fixture
def client(thing_model: type[PublicCodeModel]) -> TestClient:
    return TestClient(_api(thing_model))


@pytest.fixture
def thing(thing_model: type[PublicCodeModel]) -> PublicCodeModel:
    return thing_model._default_manager.create(label="made-up one")


def _loose_forms(code: str) -> list[str]:
    compact = code.replace("-", "")
    return [
        code,
        code.lower(),
        compact,
        compact.lower(),
        compact[1:],
        code[2:],
        f"{compact[:1]} {compact[1:5]} {compact[5:]}",
    ]


def test_existing_code_resolves_in_loose_forms(
    client: TestClient, thing: PublicCodeModel
) -> None:
    for raw in _loose_forms(thing.public_code):
        response = client.get(f"/things/{raw}")

        assert response.status_code == 200, raw
        assert response.json() == {
            "public_code": thing.public_code,
            "label": "made-up one",
        }


def _assert_not_found(client: TestClient, raw: str) -> bytes:
    response = client.get(f"/things/{raw}")

    assert response.status_code == 404, raw
    assert response.json() == NOT_FOUND
    content: bytes = response.content
    return content


def test_wrong_prefix_is_not_found(client: TestClient, thing: PublicCodeModel) -> None:
    body = thing.public_code[2:]
    club = "C" + body.replace("-", "")

    _assert_not_found(client, club)


def test_one_wrong_character_is_not_found(
    client: TestClient, thing_model: type[PublicCodeModel], thing: PublicCodeModel
) -> None:
    compact = thing.public_code.replace("-", "")
    last = compact[-2]
    other = codes.ALPHABET[(codes.ALPHABET.index(last) + 1) % 32]
    changed = compact[:-2] + other + compact[-1]

    _assert_not_found(client, changed)


def test_no_one_character_mistype_resolves_to_any_record(
    client: TestClient, thing_model: type[PublicCodeModel]
) -> None:
    # Fill the table, then mistype one record's code in every position
    # with every other character. None may resolve, to it or another one.
    things = [
        thing_model._default_manager.create(label=f"made-up {n}") for n in range(20)
    ]
    compact = things[0].public_code.replace("-", "")
    for position in range(1, len(compact)):
        for char in codes.ALPHABET:
            if char == compact[position]:
                continue
            changed = compact[:position] + char + compact[position + 1 :]

            _assert_not_found(client, changed)


def test_external_six_character_id_is_not_found(client: TestClient) -> None:
    _assert_not_found(client, "AB12CD")


def test_unknown_valid_code_is_not_found(client: TestClient) -> None:
    _assert_not_found(client, codes.generate(CodeType.PLAYER))


@pytest.mark.parametrize(
    "raw",
    ["x", "P-7K3M-QX9", "P-7K3M-QX9HH", "P%C4%B1", "P-7K3M-QXUH", "0" * 80],
)
def test_malformed_code_is_not_found(client: TestClient, raw: str) -> None:
    _assert_not_found(client, raw)


def test_malformed_and_unknown_responses_are_identical(client: TestClient) -> None:
    unknown = _assert_not_found(client, codes.generate(CodeType.PLAYER))
    malformed = _assert_not_found(client, "AB12CD")

    assert malformed == unknown


def test_openapi_documents_the_code_as_a_plain_string(
    thing_model: type[PublicCodeModel],
) -> None:
    schema = _api(thing_model).get_openapi_schema(path_prefix="")

    operation = schema["paths"]["/things/{code}"]["get"]
    [parameter] = operation["parameters"]
    assert parameter["in"] == "path"
    assert parameter["name"] == "code"
    param_schema: dict[str, Any] = parameter["schema"]
    assert param_schema["type"] == "string"
    assert "pattern" not in param_schema
    assert "maxLength" not in param_schema
    [example] = param_schema["examples"]
    assert codes.normalize(example, CodeType.PLAYER) == example
    assert "OPEN Code" in param_schema["description"]


def test_get_by_public_code_returns_the_record(
    thing_model: type[PublicCodeModel], thing: PublicCodeModel
) -> None:
    found = get_by_public_code(thing_model._default_manager.all(), thing.public_code)

    assert found.pk == thing.pk


def test_public_code_path_examples_are_valid_for_every_type() -> None:
    for code_type in CodeType:
        example = PublicCodePath(code_type).example

        assert example.startswith(code_type.prefix + "-")
        assert codes.normalize(example, code_type) == example
