"""Contract test for POST /auth/login, POST /auth/refresh per
contracts/auth-api.md."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member
from app.domains.member.security import hash_password

pytestmark = pytest.mark.asyncio


async def _make_member(
    session: AsyncSession, email: str, user_number: str, *, verified: bool = False
) -> Member:
    member = Member(
        email=email,
        password_hash=hash_password("abc12345"),
        user_number=user_number,
        verification_status="verified" if verified else "unverified",
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def test_login_succeeds_with_correct_credentials(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_member(db_session, "login@example.com", "aB3dEfGh")

    response = await client.post(
        "/auth/login", json={"email": "login@example.com", "password": "abc12345"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["member"]["email"] == "login@example.com"


async def test_login_succeeds_even_when_unverified(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_member(db_session, "unverified@example.com", "cD4eFgHi")

    response = await client.post(
        "/auth/login", json={"email": "unverified@example.com", "password": "abc12345"}
    )
    assert response.status_code == 200
    assert response.json()["member"]["verification_status"] == "unverified"


async def test_login_rejects_wrong_password(client: AsyncClient, db_session: AsyncSession) -> None:
    await _make_member(db_session, "wrongpw@example.com", "eF5gHiJk")

    response = await client.post(
        "/auth/login", json={"email": "wrongpw@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"


async def test_login_rejects_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "abc12345"}
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"


async def test_refresh_issues_new_access_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_member(db_session, "refresh@example.com", "gH6iJkLm")
    login_response = await client.post(
        "/auth/login", json={"email": "refresh@example.com", "password": "abc12345"}
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_refresh_rejects_access_token(client: AsyncClient, db_session: AsyncSession) -> None:
    await _make_member(db_session, "refresh2@example.com", "iJ7kLmNo")
    login_response = await client.post(
        "/auth/login", json={"email": "refresh2@example.com", "password": "abc12345"}
    )
    access_token = login_response.json()["access_token"]

    response = await client.post("/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401
    assert response.json()["error_code"] == "REFRESH_TOKEN_INVALID"
