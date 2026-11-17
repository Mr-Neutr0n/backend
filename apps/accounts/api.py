"""The signed-in Account, at /api/v1/accounts/ (issue #30)."""

from django.http import HttpRequest
from ninja import Router, Schema

from config.auth import account_auth

router = Router(tags=["accounts"], auth=account_auth)


class CurrentAccount(Schema):
    """The signed-in Account."""

    email: str


@router.get("/me", response=CurrentAccount, operation_id="get_current_account")
def get_current_account(request: HttpRequest) -> CurrentAccount:
    """Return the Account that the session token or session cookie belongs to."""
    return CurrentAccount(email=request.auth.email)  # type: ignore[attr-defined]
