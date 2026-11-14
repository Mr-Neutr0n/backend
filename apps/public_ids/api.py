"""API helpers for OPEN Codes in paths.

Never expose or accept a row id in the API. A path parameter that names a
record takes its public code:

    from typing import Annotated

    from apps.public_ids.api import PublicCodePath, get_by_public_code
    from apps.public_ids.codes import CodeType

    PlayerCode = Annotated[str, PublicCodePath(CodeType.PLAYER)]

    @router.get("/{code}", response=PlayerOut, operation_id="get_player")
    def get_player(request: HttpRequest, code: PlayerCode) -> Player:
        return get_by_public_code(Player.objects.all(), code)

The parameter accepts any case, spaces and hyphens, a missing prefix, and
I, L, or O for 1 or 0, and the view receives the canonical form. Malformed
input (the wrong prefix, a failed check, a 6-character external ID) raises
``Http404``, so the client gets the same 404 ``ErrorResponse`` as for a
well-formed code that matches no record: never a 422 that would tell them
which codes are well formed.
"""

from dataclasses import dataclass
from typing import Any

from django.db import models
from django.http import Http404
from django.shortcuts import get_object_or_404
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema

from apps.public_ids.codes import CodeType, check_character, format_code, normalize

# Made-up random characters for documentation examples.
_EXAMPLE_RANDOM = "7K3MQX9RD2KX3BF6"


@dataclass(frozen=True)
class PublicCodePath:
    """``Annotated`` metadata that turns a ``str`` into an OPEN Code parameter.

    The validator raises ``Http404`` rather than a validation error, and
    the OpenAPI schema is a plain string with an example: no pattern,
    which would be enforced with a 422.
    """

    code_type: CodeType

    @property
    def example(self) -> str:
        """A made-up valid code of this type, for the documentation."""
        random_part = _EXAMPLE_RANDOM[: self.code_type.length - 1]
        check = check_character(self.code_type.prefix + random_part)
        return format_code(self.code_type, random_part + check)

    def __get_pydantic_core_schema__(
        self, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_before_validator_function(
            self._resolve, handler(source_type)
        )

    def __get_pydantic_json_schema__(
        self, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {
            "type": "string",
            "description": (
                f"An OPEN Code for a {self.code_type.name.lower()}. Any case, "
                "with or without hyphens and the prefix."
            ),
            "examples": [self.example],
        }

    def _resolve(self, value: object) -> str:
        code = normalize(value, self.code_type) if isinstance(value, str) else None
        if code is None:
            raise Http404
        return code


def get_by_public_code[M: models.Model](
    queryset: models.QuerySet[M], canonical_code: str
) -> M:
    """The record with this canonical code, or ``Http404``."""
    return get_object_or_404(queryset, public_code=canonical_code)
