"""Contract test for GET /auth/verify-email/{token}, POST
/auth/resend-verification, GET /members/me, POST /auth/login per
contracts/auth-api.md (006-member-friends, extended by
020-resend-verification-email)."""

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


async def _login(client: AsyncClient, email: str, password: str = "abc12345") -> str:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    return str(response.json()["access_token"])


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
    """FR-007 (020-resend-verification-email): unchanged `require_member`
    gate, regression-tested here (`/speckit-analyze` finding L1)."""
    response = await client.post("/auth/resend-verification")
    assert response.status_code == 401
    assert response.json()["error_code"] == "MEMBER_TOKEN_INVALID"


async def test_resend_verification_first_manual_resend_succeeds_immediately_after_register(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """020-resend-verification-email (research.md #5, `/speckit-analyze`
    finding I1 fix): a member's first-ever manual resend MUST succeed even
    immediately after registration — the registration-time email does not
    count as a prior "resend". `available_at` is present and in the future
    (the cooldown for the *next* resend). A second call right after that
    one MUST be rate-limited."""
    await register(db_session, "resendc@example.com", "abc12345")
    access_token = await _login(client, "resendc@example.com")
    headers = {"Authorization": f"Bearer {access_token}"}

    first = await client.post("/auth/resend-verification", headers=headers)
    assert first.status_code == 200
    body = first.json()
    assert body["sent"] is True
    assert "available_at" in body

    second = await client.post("/auth/resend-verification", headers=headers)
    assert second.status_code == 429
    assert second.json()["error_code"] == "RESEND_RATE_LIMITED"


async def test_get_me_reports_no_cooldown_right_after_registration(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """020-resend-verification-email: `GET /members/me` MUST report
    `resend_verification_available_at: null` for a freshly-registered,
    never-manually-resent member — even though a verification email was
    already sent at registration (research.md #5)."""
    await register(db_session, "getme-fresh@example.com", "abc12345")
    access_token = await _login(client, "getme-fresh@example.com")

    response = await client.get(
        "/members/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "unverified"
    assert body["resend_verification_available_at"] is None


async def test_get_me_and_login_report_cooldown_after_a_manual_resend(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """`GET /members/me` and `POST /auth/login`'s `member` object share the
    same `MemberPublicResponse` shape (contracts/auth-api.md) — both MUST
    reflect an active cooldown after a manual resend."""
    await register(db_session, "getme-cooling@example.com", "abc12345")
    access_token = await _login(client, "getme-cooling@example.com")
    headers = {"Authorization": f"Bearer {access_token}"}
    await client.post("/auth/resend-verification", headers=headers)

    me_response = await client.get("/members/me", headers=headers)
    assert me_response.json()["resend_verification_available_at"] is not None

    login_response = await client.post(
        "/auth/login", json={"email": "getme-cooling@example.com", "password": "abc12345"}
    )
    assert login_response.json()["member"]["resend_verification_available_at"] is not None


async def test_get_me_reports_null_cooldown_for_verified_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    member = await register(db_session, "getme-verified@example.com", "abc12345")
    token = await _get_token(db_session, member.id)
    await client.get(f"/auth/verify-email/{token.token}")
    access_token = await _login(client, "getme-verified@example.com")

    response = await client.get(
        "/members/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    body = response.json()
    assert body["verification_status"] == "verified"
    assert body["resend_verification_available_at"] is None
