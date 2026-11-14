"""The API never accepts or returns a row id: records go by OPEN Code.

The guard walks the OpenAPI document, hidden operations included, and
reports every parameter, request body property, or response property named
like a row id (``id``, ``pk``, ``*_id``, ``*Id``, and their plurals) whose
type is a number or an array of numbers. String ids are out of scope: a
string cannot be told apart from a code. See ADR 0008.
"""

import uuid
from typing import Any

from django.http import HttpRequest
from ninja import Query, Schema
from ninja.operation import Operation

from config.api import OpenNinjaAPI, api

_REF_PREFIX = "#/components/schemas/"


def _is_row_id_name(name: str) -> bool:
    """``id``, ``pk``, their plurals, and ``*_id``, ``*_ids``, ``*Id``, ``*Ids``."""
    return name.lower() in {"id", "ids", "pk", "pks"} or name.endswith(
        ("_id", "_ids", "Id", "Ids")
    )


def _resolve(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith(_REF_PREFIX):
        resolved: dict[str, Any] = components[ref.removeprefix(_REF_PREFIX)]
        return resolved
    return schema


def _alternatives(schema: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        alternative
        for key in ("anyOf", "oneOf", "allOf")
        for alternative in schema.get(key, [])
    ]


def _is_integer(schema: dict[str, Any], components: dict[str, Any]) -> bool:
    """Whether the schema is a number, or an array of numbers.

    String ids are out of scope: a string cannot be told apart from a code.
    """
    schema = _resolve(schema, components)
    kind = schema.get("type")
    kinds = set(kind) if isinstance(kind, list) else {kind}
    if kinds & {"integer", "number"}:
        return True
    items = schema.get("items")
    if isinstance(items, dict) and _is_integer(items, components):
        return True
    return any(_is_integer(item, components) for item in _alternatives(schema))


def _walk(
    schema: dict[str, Any],
    components: dict[str, Any],
    where: str,
    seen: set[str],
    found: list[str],
) -> None:
    ref = schema.get("$ref")
    if isinstance(ref, str):
        if ref in seen:
            return
        seen = seen | {ref}
    schema = _resolve(schema, components)
    for name, prop in schema.get("properties", {}).items():
        if _is_row_id_name(name) and _is_integer(prop, components):
            found.append(f"{where}.{name}")
        _walk(prop, components, f"{where}.{name}", seen, found)
    for key in ("items", "additionalProperties"):
        child = schema.get(key)
        if isinstance(child, dict):
            _walk(child, components, f"{where}[]", seen, found)
    for alternative in _alternatives(schema):
        _walk(alternative, components, where, seen, found)


def _json_schemas(holder: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        media["schema"]
        for media in holder.get("content", {}).values()
        if isinstance(media.get("schema"), dict)
    ]


def row_ids_in(document: dict[str, Any]) -> list[str]:
    """Every integer id the document's operations accept or return."""
    components = document.get("components", {}).get("schemas", {})
    found: list[str] = []
    for path, path_item in document.get("paths", {}).items():
        for method, operation in path_item.items():
            where = f"{method.upper()} {path}"
            for parameter in operation.get("parameters", []):
                name = parameter["name"]
                if _is_row_id_name(name) and _is_integer(
                    parameter.get("schema", {}), components
                ):
                    found.append(f"{where} {parameter['in']} {name}")
            for schema in _json_schemas(operation.get("requestBody", {})):
                _walk(schema, components, f"{where} body", set(), found)
            for status, response in operation.get("responses", {}).items():
                for schema in _json_schemas(response):
                    _walk(schema, components, f"{where} {status}", set(), found)
    return found


def _operations(target: OpenNinjaAPI) -> list[Operation]:
    """Every operation of every router mounted on the API."""
    return [
        operation
        for bound_router in target._get_bound_routers()
        for path_view in bound_router.path_operations.values()
        for operation in path_view.operations
    ]


def row_ids_in_api(target: OpenNinjaAPI) -> list[str]:
    """Every integer id the API's operations accept or return.

    Operations left out of the document (``include_in_schema=False``) are
    put in for the walk, so a hidden operation cannot slip a row id past.
    """
    hidden = [op for op in _operations(target) if not op.include_in_schema]
    for operation in hidden:
        operation.include_in_schema = True
    try:
        document: dict[str, Any] = dict(target.get_openapi_schema(path_prefix=""))
    finally:
        for operation in hidden:
            operation.include_in_schema = False
    return row_ids_in(document)


def test_the_api_exposes_no_row_ids() -> None:
    assert row_ids_in_api(api) == []


class _Owner(Schema):
    owner_id: int
    name: str


class _Leaky(Schema):
    id: int
    ids: list[int] | None = None
    public_code: str
    owners: list[_Owner]
    parent: _Owner | None = None
    playerId: int = 0
    rank_id: float = 0
    # A string id is out of scope: it cannot be told apart from a code.
    code_id: str = ""
    # A cycle: the walker must stop, not recurse forever.
    children: list["_Leaky"] | None = None


class _CreateIn(Schema):
    club_id: int | None = None
    player_ids: list[int] | None = None
    playerIds: list[int] | None = None


def test_the_guard_reports_integer_ids() -> None:
    leaky_api = OpenNinjaAPI(urls_namespace=f"test-{uuid.uuid4().hex}")

    @leaky_api.get("/things/{pk}", response=_Leaky, operation_id="get_leaky")
    def get_leaky(
        request: HttpRequest,
        pk: int,
        player_id: Query[list[int] | None] = None,
        club_id: int = 0,
    ) -> None:
        return None

    @leaky_api.post("/things", response={201: list[_Leaky]}, operation_id="make")
    def make(request: HttpRequest, payload: _CreateIn) -> None:
        return None

    @leaky_api.get("/hidden/{pk}", operation_id="hidden", include_in_schema=False)
    def hidden(request: HttpRequest, pk: int) -> None:
        return None

    @leaky_api.get("/fine/{code}", operation_id="fine")
    def fine(request: HttpRequest, code: str, valid_id: str = "") -> int:
        return 1

    found = row_ids_in_api(leaky_api)

    response_fields = [
        "id",
        "ids",
        "owners[].owner_id",
        "parent.owner_id",
        "playerId",
        "rank_id",
    ]
    assert sorted(found) == sorted(
        [
            "GET /things/{pk} path pk",
            "GET /things/{pk} query player_id",
            "GET /things/{pk} query club_id",
            *(f"GET /things/{{pk}} 200.{field}" for field in response_fields),
            "POST /things body.club_id",
            "POST /things body.player_ids",
            "POST /things body.playerIds",
            *(f"POST /things 201[].{field}" for field in response_fields),
            "GET /hidden/{pk} path pk",
        ]
    )
    # The hidden operation stays hidden afterwards.
    assert "/hidden/{pk}" not in leaky_api.get_openapi_schema(path_prefix="")["paths"]
