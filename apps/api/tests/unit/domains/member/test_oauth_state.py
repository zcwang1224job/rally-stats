"""Unit test: `issue_oauth_state()`/`decode_oauth_state()` — the signed-JWT
`state` parameter that carries an OAuth handshake's context across the
redirect to Google/LINE and back, without any server-side storage
(research.md #2)."""

import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.errors import ApiError
from app.domains.member.security import JWT_ALGORITHM, decode_oauth_state, issue_oauth_state


def test_state_round_trips_all_fields() -> None:
    state = issue_oauth_state(
        provider="google",
        intent="login",
        code_verifier="verifier-abc",
        nonce="nonce-xyz",
    )
    decoded = decode_oauth_state(state)
    assert decoded.provider == "google"
    assert decoded.intent == "login"
    assert decoded.code_verifier == "verifier-abc"
    assert decoded.nonce == "nonce-xyz"
    assert decoded.member_id is None


def test_state_round_trips_member_id_for_link_intent() -> None:
    state = issue_oauth_state(
        provider="line",
        intent="link",
        code_verifier="verifier-def",
        nonce="nonce-uvw",
        member_id="11111111-1111-1111-1111-111111111111",
    )
    decoded = decode_oauth_state(state)
    assert decoded.intent == "link"
    assert decoded.member_id == "11111111-1111-1111-1111-111111111111"


def test_tampered_state_is_rejected() -> None:
    state = issue_oauth_state(
        provider="google", intent="login", code_verifier="v", nonce="n"
    )
    tampered = state[:-1] + ("A" if state[-1] != "A" else "B")

    with pytest.raises(ApiError) as exc_info:
        decode_oauth_state(tampered)
    assert exc_info.value.error_code == "OAUTH_STATE_INVALID"


def test_expired_state_is_rejected() -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "type": "oauth_state",
        "provider": "google",
        "intent": "login",
        "code_verifier": "v",
        "nonce": "n",
        "member_id": None,
        "iat": now - timedelta(minutes=20),
        "exp": now - timedelta(minutes=10),
    }
    expired_state = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)

    with pytest.raises(ApiError) as exc_info:
        decode_oauth_state(expired_state)
    assert exc_info.value.error_code == "OAUTH_STATE_INVALID"


def test_state_with_wrong_type_claim_is_rejected() -> None:
    """A token issued for a different purpose (e.g. an access token) MUST
    NOT be accepted as an OAuth state, mirroring `_decode_token()`'s
    `expected_type` guard."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "type": "access",
        "member_id": "11111111-1111-1111-1111-111111111111",
        "token_version": 0,
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    wrong_type_token = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)

    with pytest.raises(ApiError) as exc_info:
        decode_oauth_state(wrong_type_token)
    assert exc_info.value.error_code == "OAUTH_STATE_INVALID"


def test_state_expires_after_configured_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check that `oauth_state_ttl_minutes` actually bounds the
    token's lifetime rather than reusing the access/refresh TTLs."""
    get_settings.cache_clear()
    monkeypatch.setenv("OAUTH_STATE_TTL_MINUTES", "0")
    try:
        get_settings.cache_clear()
        state = issue_oauth_state(
            provider="google", intent="login", code_verifier="v", nonce="n"
        )
        time.sleep(1)
        with pytest.raises(ApiError) as exc_info:
            decode_oauth_state(state)
        assert exc_info.value.error_code == "OAUTH_STATE_INVALID"
    finally:
        get_settings.cache_clear()
