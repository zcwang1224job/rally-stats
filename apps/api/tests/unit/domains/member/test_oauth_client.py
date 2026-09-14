"""Unit tests for `oauth_client.exchange_code_for_profile()` — the one
piece of the OAuth flow every other test in this feature monkeypatches
around entirely. These tests exercise real `authlib` JWT signing/
verification (no live network — `httpx.AsyncClient.post`/`.get` are
monkeypatched at the class level, since the function under test constructs
its own client internally).

Added after two real bugs surfaced only via live testing against actual
Google/LINE accounts (neither existing test caught them, because nothing
exercised real JWT verification before this file):

1. `claims.validate()` had zero clock-skew tolerance (authlib's default),
   which spuriously rejected a real Google id_token as "issued in the
   future" after a Docker Desktop VM clock lagged post-sleep-resume.
2. `_ALLOWED_ALGORITHMS` was hardcoded to `["RS256"]` (Google's scheme).
   LINE Login signs its id_token with `HS256` by default (HMAC via the
   channel secret, no JWKS involved) — every real LINE login failed
   signature verification outright until `_peek_alg()` was added to route
   per-token instead of assuming one provider's scheme for both."""

import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from authlib.jose import JsonWebKey
from authlib.jose import jwt as authlib_jwt

from app.core.errors import ApiError
from app.domains.member.oauth_client import (
    OAuthProfile,
    _peek_alg,
    _redact_token_response,
    exchange_code_for_profile,
)
from app.domains.member.oauth_providers import OAuthProviderConfig

pytestmark = pytest.mark.asyncio


async def _exchange() -> OAuthProfile:
    return await exchange_code_for_profile(
        _CONFIG,
        code="c",
        code_verifier="v",
        redirect_uri="https://app.example/cb",
        nonce="expected-nonce",
    )

_CONFIG = OAuthProviderConfig(
    name="google",
    authorize_url="https://example.com/authorize",
    token_url="https://example.com/token",
    jwks_url="https://example.com/certs",
    issuer="https://example.com",
    client_id="test-client-id",
    client_secret="test-client-secret",
    scopes="openid email profile",
)


def _rsa_id_token(claims: dict[str, object]) -> tuple[bytes, dict[str, object]]:
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    token = authlib_jwt.encode({"alg": "RS256", "kid": "kid-1"}, claims, key)
    import json as jsonlib

    public_jwk = jsonlib.loads(key.as_json(is_private=False))
    public_jwk["kid"] = "kid-1"
    return token, {"keys": [public_jwk]}


def _hmac_id_token(claims: dict[str, object], secret: str) -> bytes:
    return authlib_jwt.encode({"alg": "HS256"}, claims, secret)


def _base_claims(**overrides: object) -> dict[str, object]:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": _CONFIG.issuer,
        "aud": _CONFIG.client_id,
        "sub": "user-123",
        "iat": now,
        "exp": now + 3600,
        "nonce": "expected-nonce",
        "email": "user@example.com",
    }
    claims.update(overrides)
    return claims


def _mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    *,
    id_token: bytes,
    jwks: dict[str, object] | None = None,
    token_status: int = 200,
) -> None:
    async def fake_post(self: httpx.AsyncClient, url: str, **_kwargs: object) -> httpx.Response:
        assert url == _CONFIG.token_url
        return httpx.Response(token_status, json={"id_token": id_token.decode()})

    async def fake_get(self: httpx.AsyncClient, url: str, **_kwargs: object) -> httpx.Response:
        assert url == _CONFIG.jwks_url
        return httpx.Response(200, json=jwks or {"keys": []})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


async def test_peek_alg_reads_header_without_verifying() -> None:
    rs_token, _ = _rsa_id_token(_base_claims())
    hs_token = _hmac_id_token(_base_claims(), "secret")
    assert _peek_alg(rs_token.decode()) == "RS256"
    assert _peek_alg(hs_token.decode()) == "HS256"
    assert _peek_alg("not-a-jwt") is None


async def test_rs256_id_token_verifies_via_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Google's scheme."""
    token, jwks = _rsa_id_token(_base_claims())
    _mock_transport(monkeypatch, id_token=token, jwks=jwks)

    profile = await _exchange()

    assert profile.sub == "user-123"
    assert profile.email == "user@example.com"


async def test_hs256_id_token_verifies_via_client_secret_no_jwks_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LINE's default scheme (research.md addendum, 2026-09-14) — MUST NOT
    fetch the JWKS endpoint at all for an HS256 token."""
    token = _hmac_id_token(_base_claims(), _CONFIG.client_secret)

    async def fake_post(self: httpx.AsyncClient, url: str, **_kwargs: object) -> httpx.Response:
        return httpx.Response(200, json={"id_token": token.decode()})

    async def fail_get(self: httpx.AsyncClient, url: str, **_kwargs: object) -> httpx.Response:
        raise AssertionError("JWKS endpoint MUST NOT be called for an HS256 id_token")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fail_get)

    profile = await _exchange()

    assert profile.sub == "user-123"


async def test_hs256_token_signed_with_wrong_secret_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _hmac_id_token(_base_claims(), "not-the-real-secret")
    _mock_transport(monkeypatch, id_token=token)

    with pytest.raises(ApiError) as exc_info:
        await _exchange()
    assert exc_info.value.error_code == "OAUTH_PROVIDER_ERROR"


async def test_clock_skew_within_leeway_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """research.md addendum: a container clock a little behind real time
    MUST NOT spuriously reject a fresh, otherwise-valid id_token."""
    future_iat = int((datetime.now(UTC) + timedelta(seconds=30)).timestamp())
    token, jwks = _rsa_id_token(_base_claims(iat=future_iat))
    _mock_transport(monkeypatch, id_token=token, jwks=jwks)

    profile = await _exchange()

    assert profile.sub == "user-123"


async def test_clock_skew_beyond_leeway_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    far_future_iat = int((datetime.now(UTC) + timedelta(minutes=10)).timestamp())
    token, jwks = _rsa_id_token(_base_claims(iat=far_future_iat))
    _mock_transport(monkeypatch, id_token=token, jwks=jwks)

    with pytest.raises(ApiError) as exc_info:
        await _exchange()
    assert exc_info.value.error_code == "OAUTH_PROVIDER_ERROR"


async def test_nonce_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    token, jwks = _rsa_id_token(_base_claims(nonce="different-nonce"))
    _mock_transport(monkeypatch, id_token=token, jwks=jwks)

    with pytest.raises(ApiError) as exc_info:
        await _exchange()
    assert exc_info.value.error_code == "OAUTH_PROVIDER_ERROR"


async def test_wrong_audience_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    token, jwks = _rsa_id_token(_base_claims(aud="someone-elses-client-id"))
    _mock_transport(monkeypatch, id_token=token, jwks=jwks)

    with pytest.raises(ApiError) as exc_info:
        await _exchange()
    assert exc_info.value.error_code == "OAUTH_PROVIDER_ERROR"


async def test_wrong_issuer_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    token, jwks = _rsa_id_token(_base_claims(iss="https://not-the-real-issuer.example"))
    _mock_transport(monkeypatch, id_token=token, jwks=jwks)

    with pytest.raises(ApiError) as exc_info:
        await _exchange()
    assert exc_info.value.error_code == "OAUTH_PROVIDER_ERROR"


async def test_missing_email_claim_yields_none(monkeypatch: pytest.MonkeyPatch) -> None:
    claims = _base_claims()
    del claims["email"]
    token, jwks = _rsa_id_token(claims)
    _mock_transport(monkeypatch, id_token=token, jwks=jwks)

    profile = await _exchange()

    assert profile.email is None


async def test_non_200_token_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    token, _ = _rsa_id_token(_base_claims())
    _mock_transport(monkeypatch, id_token=token, token_status=400)

    with pytest.raises(ApiError) as exc_info:
        await _exchange()
    assert exc_info.value.error_code == "OAUTH_PROVIDER_ERROR"


# --- Security: a live access_token MUST NEVER end up in a log line -------


async def test_redact_token_response_strips_bearer_credentials() -> None:
    """A 200 response missing `id_token` can still legitimately carry a
    live `access_token`/`refresh_token` — the diagnostic log line built
    from this function MUST NOT be able to leak one into `docker logs` (and
    from there, CloudWatch in production)."""
    response = httpx.Response(
        200,
        json={
            "access_token": "ya29.super-secret-live-access-token",
            "refresh_token": "1//super-secret-refresh-token",
            "token_type": "Bearer",
            "scope": "openid email",
            "expires_in": 3600,
        },
    )

    redacted = _redact_token_response(response)

    assert "super-secret-live-access-token" not in redacted
    assert "super-secret-refresh-token" not in redacted
    assert '"token_type": "Bearer"' in redacted
    assert '"scope": "openid email"' in redacted
    assert "access_token" in redacted  # the field NAME may appear in <redacted_fields>
    assert "refresh_token" in redacted


async def test_redact_token_response_keeps_error_fields_for_debugging() -> None:
    response = httpx.Response(
        400, json={"error": "invalid_grant", "error_description": "Malformed auth code."}
    )

    redacted = _redact_token_response(response)

    assert "invalid_grant" in redacted
    assert "Malformed auth code." in redacted


async def test_redact_token_response_handles_non_json_body() -> None:
    response = httpx.Response(502, text="<html>Bad Gateway</html>")

    redacted = _redact_token_response(response)

    assert "<html>" not in redacted
    assert "non-JSON response" in redacted


async def test_access_token_never_appears_in_logs_on_missing_id_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """End-to-end version of the two tests above: drives the real failure
    path (200 response, no `id_token`) with a realistic live-looking
    `access_token` alongside it, and asserts it never reaches the logger."""

    async def fake_post(self: httpx.AsyncClient, url: str, **_kwargs: object) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "ya29.super-secret-live-access-token",
                "token_type": "Bearer",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with caplog.at_level("ERROR"):
        with pytest.raises(ApiError):
            await _exchange()

    assert "super-secret-live-access-token" not in caplog.text
