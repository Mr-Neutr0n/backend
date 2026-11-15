"""The django-oauth-toolkit views OPEN serves, under ``/oauth/``.

Only the token and revoke endpoints: partners use client credentials
(#28 sets the grant types and scopes). DOT's authorize, application
management, introspection, device, OpenID Connect, and registration
views are left out, so their paths return 404.
"""

from django.urls import URLPattern, path
from oauth2_provider.views import RevokeTokenView, TokenView

app_name = "oauth2_provider"

urlpatterns: list[URLPattern] = [
    path("token/", TokenView.as_view(), name="token"),
    path("revoke_token/", RevokeTokenView.as_view(), name="revoke-token"),
]
