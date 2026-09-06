"""Contract test for POST /auth/forgot-password, POST
/auth/reset-password/{token} per contracts/auth-api.md."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import PasswordResetToken
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def test_forgot_password_returns_same_response_for_unknown_email(
    client: AsyncClient,
) -> None:
    response = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert response.status_code == 200
    assert response.json() == {"sent": True}


async def test_forgot_password_returns_same_response_for_known_email(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(db_session, "known-fp@example.com", "abc12345")

    response = await client.post(
        "/auth/forgot-password", json={"email": "known-fp@example.com"}
    )
    assert response.status_code == 200
    assert response.json() == {"sent": True}


async def test_reset_password_succeeds(client: AsyncClient, db_session: AsyncSession) -> None:
    member = await register(db_session, "reset-c@example.com", "abc12345")
    await client.post("/auth/forgot-password", json={"email": "reset-c@example.com"})

    result = await db_session.execute(
        select(PasswordResetToken).where(PasswordResetToken.member_id == member.id)
    )
    token = result.scalar_one()

    response = await client.post(
        f"/auth/reset-password/{token.token}",
        json={"new_password": "newpass123", "confirm_new_password": "newpass123"},
    )
    assert response.status_code == 200
    assert response.json()["reset"] is True

    login_response = await client.post(
        "/auth/login", json={"email": "reset-c@example.com", "password": "newpass123"}
    )
    assert login_response.status_code == 200


async def test_reset_password_rejects_mismatched_confirmation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(db_session, "reset-mismatch@example.com", "abc12345")
    await client.post("/auth/forgot-password", json={"email": "reset-mismatch@example.com"})
    result = await db_session.execute(select(PasswordResetToken))
    token = result.scalars().first()

    response = await client.post(
        f"/auth/reset-password/{token.token}",
        json={"new_password": "newpass123", "confirm_new_password": "different123"},
    )
    assert response.status_code == 422


async def test_reset_password_rejects_unknown_token(client: AsyncClient) -> None:
    response = await client.post(
        f"/auth/reset-password/{uuid.uuid4()}",
        json={"new_password": "newpass123", "confirm_new_password": "newpass123"},
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "RESET_TOKEN_INVALID"
