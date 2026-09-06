"""Contract test for POST /auth/register per contracts/auth-api.md."""

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def test_register_succeeds(client: AsyncClient, valid_turnstile_token: str) -> None:
    response = await client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "newuser@example.com"
    assert len(body["user_number"]) == 8


async def test_register_rejects_turnstile_failure(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    # Cloudflare's "always-pass" test secret key (used by the rest of this
    # suite) accepts any token content, so simulate a rejection directly
    # instead — same pattern as test_create_group.py.
    async def _fail_verify(token: str, remote_ip: str | None = None) -> None:
        raise ApiError("CAPTCHA_INVALID", status_code=400)

    monkeypatch.setattr("app.domains.member.router.verify_turnstile_token", _fail_verify)

    response = await client.post(
        "/auth/register",
        json={
            "email": "newuser2@example.com",
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": "invalid-token",
        },
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "CAPTCHA_INVALID"


async def test_register_rejects_password_mismatch(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    response = await client.post(
        "/auth/register",
        json={
            "email": "newuser3@example.com",
            "password": "abc12345",
            "confirm_password": "different123",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 422


async def test_register_rejects_weak_password(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    response = await client.post(
        "/auth/register",
        json={
            "email": "newuser4@example.com",
            "password": "onlyletters",
            "confirm_password": "onlyletters",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 422


async def test_register_rejects_duplicate_email(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    await register(db_session, "existing@example.com", "abc12345")

    response = await client.post(
        "/auth/register",
        json={
            "email": "existing@example.com",
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "EMAIL_ALREADY_REGISTERED"
