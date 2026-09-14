"""Per-provider OAuth/OIDC configuration — specs/027-google-line-oauth-login
research.md #3. Router/service code only ever talks to `provider: Literal
["google", "line"]` plus this small config table; no provider-specific
if/else branches are allowed to leak into `service.py`/`router.py`
(constitution VI, plan.md Constitution Check row VI)."""

from dataclasses import dataclass
from typing import Literal

from app.core.config import get_settings

Provider = Literal["google", "line"]


@dataclass(frozen=True)
class OAuthProviderConfig:
    name: Provider
    authorize_url: str
    token_url: str
    jwks_url: str
    issuer: str
    client_id: str
    client_secret: str
    scopes: str


def _google() -> OAuthProviderConfig:
    settings = get_settings()
    return OAuthProviderConfig(
        name="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        jwks_url="https://www.googleapis.com/oauth2/v3/certs",
        issuer="https://accounts.google.com",
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        scopes="openid email profile",
    )


def _line() -> OAuthProviderConfig:
    settings = get_settings()
    return OAuthProviderConfig(
        name="line",
        authorize_url="https://access.line.me/oauth2/v2.1/authorize",
        token_url="https://api.line.me/oauth2/v2.1/token",
        jwks_url="https://api.line.me/oauth2/v2.1/certs",
        issuer="https://access.line.me",
        client_id=settings.line_oauth_channel_id,
        client_secret=settings.line_oauth_channel_secret,
        # research.md #9: LINE's `email` scope is optional and may require
        # separate approval in the LINE Developers Console — the user can
        # also decline it at consent time (FR-004). Google's `email` scope
        # is effectively always granted (a Google account *is* an email
        # address), so no such branch exists for Google.
        scopes="openid email profile",
    )


def get_provider_config(provider: Provider) -> OAuthProviderConfig:
    if provider == "google":
        return _google()
    return _line()
