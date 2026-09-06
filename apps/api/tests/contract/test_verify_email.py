"""Contract test for GET /auth/verify-email/{token}, POST
/auth/resend-verification per contracts/auth-api.md."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import EmailVerificationToken
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _get_token(session: AsyncSession, member_id: object) -> EmailVerificationToken:
    result = await session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member_id)
    )
    return result.scalar_one()


async def test_verify_email_succeeds(client: AsyncClient, db_session: AsyncSession) -> None:
    member = await register(db_session, "verifyc@example.com", "abc12345")
    token = await _get_token(db_session, member.id)

    response = await client.get(f"/auth/verify-email/{token.token}")
    assert response.status_code == 200
    assert response.json()["verified"] is True


async def test_verify_email_rejects_unknown_token(client: AsyncClient) -> None:
    response = await client.get(f"/auth/verify-email/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error_code"] == "VERIFICATION_TOKEN_INVALID"


async def test_resend_verification_requires_login(client: AsyncClient) -> None:
    response = await client.post("/auth/resend-verification")
    assert response.status_code == 401


async def test_resend_verification_rate_limited_immediately_after_register(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(db_session, "resendc@example.com", "abc12345")
    login_response = await client.post(
        "/auth/login", json={"email": "resendc@example.com", "password": "abc12345"}
    )
    access_token = login_response.json()["access_token"]

    response = await client.post(
        "/auth/resend-verification", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 429
    assert response.json()["error_code"] == "RESEND_RATE_LIMITED"
