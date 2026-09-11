"""Integration test: 020-resend-verification-email end-to-end through the
real HTTP layer, per quickstart.md 情境 2/5 — register → first manual
resend succeeds immediately (research.md #5, fixing `/speckit-analyze`
finding I1) → a second resend within 5 minutes is rate-limited → succeeds
again once 5 minutes have passed."""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import EmailVerificationToken, Member

pytestmark = pytest.mark.asyncio


async def _register_and_login(
    client: AsyncClient, db_session: AsyncSession, email: str, turnstile_token: str
) -> tuple[str, Member]:
    password = "abc12345"
    register_response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "confirm_password": password,
            "turnstile_token": turnstile_token,
        },
    )
    assert register_response.status_code == 201

    member_result = await db_session.execute(select(Member).where(Member.email == email))
    member = member_result.scalar_one()

    login_response = await client.post("/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200
    return str(login_response.json()["access_token"]), member


async def test_first_resend_succeeds_then_blocked_then_succeeds_after_cooldown(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    access_token, member = await _register_and_login(
        client, db_session, "resend-flow-1@example.com", valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {access_token}"}

    # quickstart.md 情境 5: member has exactly 1 token (registration) —
    # the first manual resend MUST succeed immediately, MUST NOT be
    # mistaken for a cooldown violation.
    first_resend = await client.post("/auth/resend-verification", headers=headers)
    assert first_resend.status_code == 200
    assert first_resend.json()["sent"] is True

    token_count_result = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
    )
    assert len(token_count_result.scalars().all()) == 2  # registration + this resend

    # quickstart.md 情境 2: a second resend within 5 minutes is rejected —
    # no third email/token is created.
    second_resend = await client.post("/auth/resend-verification", headers=headers)
    assert second_resend.status_code == 429
    assert second_resend.json()["error_code"] == "RESEND_RATE_LIMITED"

    token_count_after_rejection = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
    )
    assert len(token_count_after_rejection.scalars().all()) == 2  # unchanged

    # Fast-forward past the 5-minute cooldown by backdating every existing
    # token for this member (preserving their relative order) — a third
    # resend then succeeds.
    all_tokens_result = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
    )
    for token in all_tokens_result.scalars():
        token.created_at = token.created_at - timedelta(minutes=5, seconds=1)
    await db_session.commit()

    third_resend = await client.post("/auth/resend-verification", headers=headers)
    assert third_resend.status_code == 200

    final_count_result = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
    )
    assert len(final_count_result.scalars().all()) == 3
