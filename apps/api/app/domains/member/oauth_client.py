"""Provider-agnostic OAuth token exchange + `id_token` verification —
research.md #3. Split from service.py so the account/business logic never
touches httpx/authlib directly (constitution VI): `service.py` only ever
calls `exchange_code_for_profile()` and gets back a plain `OAuthProfile` or
an `ApiError("OAUTH_PROVIDER_ERROR")`, regardless of which provider or which
specific network/JOSE failure occurred underneath."""

import base64
import binascii
import json as jsonlib
import logging
from dataclasses import dataclass

import httpx
from authlib.jose import JsonWebToken
from authlib.jose.errors import JoseError

from app.core.errors import ApiError
from app.domains.member.oauth_providers import OAuthProviderConfig

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_SECONDS = 5.0
# Google always signs id_token with RS256 (JWKS-published RSA keys). LINE
# Login, unlike Google, defaults to HS256 (HMAC with the channel secret
# itself, no JWKS involved) unless the channel opts into an asymmetric
# "assertion signing key" (ES256, verified via its published JWKS the same
# way Google's RS256 is) — this is a per-channel LINE Developers Console
# setting, not something this code can assume in advance. `_peek_alg()`
# reads the (unverified) JWT header to route to the right verification path
# before any signature check happens; the header itself is not trusted for
# anything beyond picking *how* to verify, same as any JWKS-`kid`-based
# library resolves keys.
_JWKS_ALGORITHMS = ["RS256", "ES256"]
_HMAC_ALGORITHMS = ["HS256"]
# authlib defaults exp/iat validation to zero tolerance; the OIDC spec's own
# guidance (and every major provider's own client library) is to allow a
# small leeway for clock skew between this host and the provider's — without
# it, a container clock even a few seconds off (e.g. right after a Docker
# Desktop VM resumes from host sleep) spuriously rejects a perfectly valid
# id_token as "issued in the future".
_CLOCK_SKEW_LEEWAY_SECONDS = 60


_SAFE_TOKEN_RESPONSE_FIELDS = {"error", "error_description", "error_uri", "token_type", "scope"}


def _redact_token_response(response: httpx.Response) -> str:
    """A 200 response from the token endpoint can legitimately carry a live
    `access_token`/`refresh_token` alongside whatever made us log this in
    the first place (e.g. a missing `id_token`) — logs are read by more
    people and shipped to more places (CloudWatch in production) than the
    secrets themselves, so the raw body MUST NEVER be logged verbatim. Only
    a fixed allow-list of fields that are never bearer credentials survives."""
    try:
        body = response.json()
    except ValueError:
        return f"<non-JSON response, {len(response.content)} bytes>"
    if not isinstance(body, dict):
        return f"<unexpected response shape: {type(body).__name__}>"
    safe = {k: v for k, v in body.items() if k in _SAFE_TOKEN_RESPONSE_FIELDS}
    redacted_keys = sorted(set(body) - _SAFE_TOKEN_RESPONSE_FIELDS)
    if redacted_keys:
        safe["<redacted_fields>"] = redacted_keys
    return jsonlib.dumps(safe)


def _peek_alg(id_token: str) -> str | None:
    """Reads the `alg` header of a compact JWS **without** verifying
    anything — used only to pick which verification path to take next
    (HMAC vs. JWKS-based). Never trusted as proof of anything on its own."""
    try:
        header_b64 = id_token.split(".", 1)[0]
        padded = header_b64 + "=" * (-len(header_b64) % 4)
        header = jsonlib.loads(base64.urlsafe_b64decode(padded))
        alg = header.get("alg")
        return str(alg) if alg else None
    except (ValueError, binascii.Error, jsonlib.JSONDecodeError, UnicodeDecodeError):
        return None


@dataclass(frozen=True)
class OAuthProfile:
    sub: str
    email: str | None


async def exchange_code_for_profile(
    config: OAuthProviderConfig,
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    nonce: str,
) -> OAuthProfile:
    """Errors: `OAUTH_PROVIDER_ERROR` (502) for any transport failure,
    non-200 response, or `id_token` that fails signature/`iss`/`aud`/
    `nonce`/`exp` verification."""
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            token_response = await client.post(
                config.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                    "code_verifier": code_verifier,
                },
            )
            if token_response.status_code != 200:
                logger.error(
                    "OAuth token exchange failed provider=%s status=%s body=%s",
                    config.name,
                    token_response.status_code,
                    _redact_token_response(token_response),
                )
                raise ApiError("OAUTH_PROVIDER_ERROR", status_code=502)
            id_token = token_response.json().get("id_token")
            if not id_token:
                logger.error(
                    "OAuth token response had no id_token provider=%s body=%s",
                    config.name,
                    _redact_token_response(token_response),
                )
                raise ApiError("OAUTH_PROVIDER_ERROR", status_code=502)

            alg = _peek_alg(id_token)
            if alg in _HMAC_ALGORITHMS:
                # LINE's default: HS256, verified with the channel secret
                # itself — no JWKS fetch involved at all.
                verify_key: str | dict[str, object] = config.client_secret
                allowed_algorithms = _HMAC_ALGORITHMS
            else:
                jwks_response = await client.get(config.jwks_url)
                if jwks_response.status_code != 200:
                    logger.error(
                        "OAuth JWKS fetch failed provider=%s status=%s",
                        config.name,
                        jwks_response.status_code,
                    )
                    raise ApiError("OAUTH_PROVIDER_ERROR", status_code=502)
                verify_key = jwks_response.json()
                allowed_algorithms = _JWKS_ALGORITHMS
    except httpx.HTTPError:
        logger.exception("OAuth transport error provider=%s", config.name)
        raise ApiError("OAUTH_PROVIDER_ERROR", status_code=502) from None

    try:
        jwt = JsonWebToken(allowed_algorithms)
        claims = jwt.decode(
            id_token,
            verify_key,
            claims_options={
                "iss": {"essential": True, "values": [config.issuer]},
                "aud": {"essential": True, "values": [config.client_id]},
            },
        )
        claims.validate(leeway=_CLOCK_SKEW_LEEWAY_SECONDS)
    except JoseError:
        logger.exception(
            "OAuth id_token verification failed provider=%s alg=%s", config.name, alg
        )
        raise ApiError("OAUTH_PROVIDER_ERROR", status_code=502) from None

    if claims.get("nonce") != nonce:
        logger.error("OAuth nonce mismatch provider=%s", config.name)
        raise ApiError("OAUTH_PROVIDER_ERROR", status_code=502)

    sub = claims.get("sub")
    if not sub:
        logger.error("OAuth id_token had no sub claim provider=%s", config.name)
        raise ApiError("OAUTH_PROVIDER_ERROR", status_code=502)
    return OAuthProfile(sub=str(sub), email=claims.get("email"))
