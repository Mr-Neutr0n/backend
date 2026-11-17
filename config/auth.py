"""Account authentication for OPEN API operations (issue #30).

`account_auth` accepts either of allauth's two headless clients:

- the app client's session token, sent in the `X-Session-Token` header
  (no CSRF, since no cookie is involved), and
- the browser client's Django session cookie, with CSRF checked on unsafe
  methods (ninja's `SessionAuth`).

Pass it as an operation's or router's `auth`. The signed-in Account is in
`request.auth` (and `request.user`). A request that neither one
authenticates gets a 401 `ErrorResponse` (`config/api_errors.py`).
"""

from allauth.headless.contrib.ninja.security import XSessionTokenAuth
from ninja.security import SessionAuth


class SessionTokenAuth(XSessionTokenAuth):
    """allauth's `X-Session-Token` auth, documented as a header API key.

    allauth's class names only the scheme type, which leaves its OpenAPI
    security scheme without the required `in` and `name`.
    """

    openapi_in: str = "header"
    openapi_name: str = "X-Session-Token"


account_auth = [SessionTokenAuth(), SessionAuth()]
