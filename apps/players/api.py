"""Player endpoints at /api/v1/players/ (issue #31).

A player's match history: the player's own Account sees every match they
played, in every status. Another signed-in Account sees only confirmed
matches, and only while the player's ``match_history_visibility`` lets it
(``PlayerPrivacy.visible_to``, which also hides the history while the
player's Account is inactive). A viewer it hides the history from gets
the same 404 as an unknown or malformed code, so the response never
reveals that the player exists (ADR 0008). The status filter is in the query, so the
page's ``count`` never counts a match the viewer may not see.
"""

from typing import Annotated, Any

from django.db.models import QuerySet
from django.http import Http404, HttpRequest
from ninja import Field, Router, Schema
from ninja.pagination import LimitOffsetPagination, paginate

from apps.matches.api import request_account
from apps.matches.models import Match, MatchStatus
from apps.matches.schemas import MatchOut, match_out, with_match_details
from apps.players.models import Player
from apps.public_ids.api import PublicCodePath, get_by_public_code
from apps.public_ids.codes import CodeType
from config.api_errors import ErrorResponse
from config.auth import account_auth

router = Router(tags=["players"], auth=account_auth)

PlayerCode = Annotated[str, PublicCodePath(CodeType.PLAYER)]

HISTORY_PAGE_SIZE = 20
HISTORY_MAX_PAGE_SIZE = 100
# Postgres takes a bigint OFFSET: a larger one would fail in the database.
HISTORY_MAX_OFFSET = 2**63 - 1


class MatchHistoryPagination(LimitOffsetPagination):
    """Limit and offset paging of a match history, newest first.

    Each page's matches become ``MatchOut`` as the signed-in Account sees
    them (the Private player rule depends on the viewer).
    """

    class Input(Schema):
        limit: int = Field(HISTORY_PAGE_SIZE, ge=1, le=HISTORY_MAX_PAGE_SIZE)
        offset: int = Field(0, ge=0, le=HISTORY_MAX_OFFSET)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(max_limit=HISTORY_MAX_PAGE_SIZE, **kwargs)

    def paginate_queryset(
        self,
        queryset: QuerySet[Match],
        pagination: Any,
        request: HttpRequest,
        **params: Any,
    ) -> Any:
        page = super().paginate_queryset(queryset, pagination, request, **params)
        viewer = request_account(request)
        page[self.items_attribute] = [
            match_out(match, viewer) for match in page[self.items_attribute]
        ]
        return page


@router.get(
    "/{code}/matches",
    response={200: list[MatchOut], 404: ErrorResponse},
    operation_id="list_player_matches",
)
@paginate(MatchHistoryPagination)
def list_player_matches(request: HttpRequest, code: PlayerCode) -> QuerySet[Match]:
    """The matches a player played, newest first.

    The player sees every status. Anyone else signed in sees confirmed
    matches only, and gets 404, as for an unknown code, when the player
    keeps their match history private or their Account is inactive.
    """
    viewer = request_account(request)
    player = get_by_public_code(
        Player.objects.select_related("account", "privacy"), code
    )
    matches = Match.objects.filter(participants__player=player)
    if viewer.pk != player.account_id:
        if not player.privacy.visible_to("match_history_visibility", viewer):
            raise Http404
        matches = matches.filter(status=MatchStatus.CONFIRMED)
    return with_match_details(matches).order_by("-played_on", "-created_at", "-pk")
