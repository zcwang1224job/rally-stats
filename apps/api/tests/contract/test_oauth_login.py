"""Contract test for GET /auth/oauth/{provider}/start and
GET /auth/oauth/{provider}/callback, per
specs/027-google-line-oauth-login/contracts/oauth-login-api.md.
Covers every row of the `intent=login` callback table — /speckit-analyze
2026-09-14 remediation, finding E1: the pre-analyze draft of this task
named only 4 of the 6 branches, silently dropping `ACCOUNT_DELETED` and
`OAUTH_EMAIL_ALREADY_REGISTERED`."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.member import service
from app.domains.member.models import MemberOAuthIdentity
from app.domains.member.oauth_client import OAuthProfile
from app.domains.member.security import decode_oauth_state
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio

_FakeExchange = Callable[..., Awaitable[OAuthProfile]]


def _make_fake_exchange(profile: OAuthProfile) -> _FakeExchange:
    async def _fake(config: object, **_kwargs: object) -> OAuthProfile:
        return profile

    return _fake


def _make_failing_exchange() -> _FakeExchange:
    async def _fake(config: object, **_kwargs: object) -> OAuthProfile:
        raise ApiError("OAUTH_PROVIDER_ERROR", status_code=502)

    return _fake


async def _start_state(
    client: AsyncClient, provider: str = "google", intent: str = "login", token: str | None = None
) -> str:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = await client.get(
        f"/auth/oauth/{provider}/start", params={"intent": intent}, headers=headers
    )
    qs = parse_qs(urlparse(response.json()["authorize_url"]).query)
    return qs["state"][0]


# --- GET /auth/oauth/{provider}/start ------------------------------------


async def test_start_returns_authorize_url(client: AsyncClient) -> None:
    response = await client.get("/auth/oauth/google/start")
    assert response.status_code == 200
    parsed = urlparse(response.json()["authorize_url"])
    assert parsed.hostname == "accounts.google.com"


async def test_start_rejects_unknown_provider(client: AsyncClient) -> None:
    response = await client.get("/auth/oauth/facebook/start")
    assert response.status_code == 404


async def test_start_link_intent_requires_login(client: AsyncClient) -> None:
    response = await client.get("/auth/oauth/google/start", params={"intent": "link"})
    assert response.status_code == 401


async def test_start_link_intent_succeeds_for_verified_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    member = await register(db_session, "oauthstart@example.com", "abc12345")
    member.verification_status = "verified"
    await db_session.commit()
    login = await client.post(
        "/auth/login", json={"email": "oauthstart@example.com", "password": "abc12345"}
    )
    token = login.json()["access_token"]

    response = await client.get(
        "/auth/oauth/google/start",
        params={"intent": "link"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    qs = parse_qs(urlparse(response.json()["authorize_url"]).query)
    decoded = decode_oauth_state(qs["state"][0])
    assert decoded.intent == "link"
    assert decoded.member_id == str(member.id)


# --- GET /auth/oauth/{provider}/callback, intent=login -------------------


async def test_callback_success_new_member(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = await _start_state(client)
    profile = OAuthProfile(sub="contract-sub-1", email="contractnew@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    response = await client.get("/auth/oauth/google/callback", params={"code": "c", "state": state})

    assert response.status_code == 302
    location = response.headers["location"]
    assert "/auth/oauth-callback#" in location
    assert "status=success" in location
    assert "is_new_member=true" in location
    assert "access_token=" in location


async def test_callback_success_returning_member(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = await register(db_session, "contractreturn@example.com", "abc12345")
    member.verification_status = "verified"
    db_session.add(
        MemberOAuthIdentity(
            member_id=member.id, provider="google", provider_user_id="contract-sub-2"
        )
    )
    await db_session.commit()

    state = await _start_state(client)
    profile = OAuthProfile(sub="contract-sub-2", email="contractreturn@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    response = await client.get("/auth/oauth/google/callback", params={"code": "c", "state": state})

    assert response.status_code == 302
    location = response.headers["location"]
    assert "status=success" in location
    assert "is_new_member=false" in location


async def test_callback_cancelled(client: AsyncClient) -> None:
    state = await _start_state(client)
    response = await client.get(
        "/auth/oauth/google/callback", params={"state": state, "error": "access_denied"}
    )
    assert response.status_code == 302
    assert "status=cancelled" in response.headers["location"]


async def test_callback_state_invalid(client: AsyncClient) -> None:
    response = await client.get(
        "/auth/oauth/google/callback", params={"code": "c", "state": "garbage"}
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "status=error" in location
    assert "OAUTH_STATE_INVALID" in location


async def test_callback_provider_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = await _start_state(client)
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_failing_exchange())

    response = await client.get("/auth/oauth/google/callback", params={"code": "c", "state": state})

    assert response.status_code == 302
    assert "OAUTH_PROVIDER_ERROR" in response.headers["location"]


async def test_callback_account_deleted(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = await register(db_session, "contractdeleted@example.com", "abc12345")
    db_session.add(
        MemberOAuthIdentity(
            member_id=member.id, provider="google", provider_user_id="contract-sub-3"
        )
    )
    member.deleted_at = datetime.now(UTC)
    await db_session.commit()

    state = await _start_state(client)
    profile = OAuthProfile(sub="contract-sub-3", email="contractdeleted@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    response = await client.get("/auth/oauth/google/callback", params={"code": "c", "state": state})

    assert response.status_code == 302
    assert "ACCOUNT_DELETED" in response.headers["location"]


# --- T029 (US2): GET /auth/oauth/line/start and .../callback -------------


async def test_line_start_returns_authorize_url(client: AsyncClient) -> None:
    response = await client.get("/auth/oauth/line/start")
    assert response.status_code == 200
    parsed = urlparse(response.json()["authorize_url"])
    assert parsed.hostname == "access.line.me"


async def test_line_callback_success_new_member_without_email(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = await _start_state(client, provider="line")
    profile = OAuthProfile(sub="contract-line-sub-1", email=None)
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    response = await client.get("/auth/oauth/line/callback", params={"code": "c", "state": state})

    assert response.status_code == 302
    location = response.headers["location"]
    assert "status=success" in location
    assert "is_new_member=true" in location


async def test_callback_email_already_registered(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register(db_session, "contractcollide@example.com", "abc12345")

    state = await _start_state(client)
    profile = OAuthProfile(sub="contract-sub-4", email="contractcollide@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    response = await client.get("/auth/oauth/google/callback", params={"code": "c", "state": state})

    assert response.status_code == 302
    assert "OAUTH_EMAIL_ALREADY_REGISTERED" in response.headers["location"]
