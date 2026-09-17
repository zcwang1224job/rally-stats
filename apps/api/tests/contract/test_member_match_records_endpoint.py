"""Contract test for GET /members/me/match-records per
contracts/member-view-api.md (005-member-view US5)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member
from app.domains.member.oauth_client import OAuthProfile
from app.domains.member.service import _complete_oauth_login, register

pytestmark = pytest.mark.asyncio


async def _register(session: AsyncSession, email: str, *, verified: bool = True) -> Member:
    """Verified by default: match records are locked until the e-mail is
    verified (constitution IV), so an unverified member can't reach any of
    the behaviour under test here."""
    member = await register(session, email, "abc12345")
    if verified:
        member.verification_status = "verified"
        await session.commit()
    return member


async def _login(client: AsyncClient, email: str, password: str = "abc12345") -> str:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    return str(response.json()["access_token"])


async def test_member_match_records_succeeds(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(db_session, "matchrecords@example.com")
    access_token = await _login(client, "matchrecords@example.com")

    response = await client.get(
        "/members/me/match-records", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["matches"] == []
    assert body["total_matches"] == 0
    assert body["win_rate"] == 0.0


async def test_member_match_records_requires_login(client: AsyncClient) -> None:
    response = await client.get("/members/me/match-records")
    assert response.status_code == 401
    assert response.json()["error_code"] == "MEMBER_TOKEN_INVALID"


async def test_member_match_records_rejects_non_positive_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(db_session, "matchrecords-page@example.com")
    access_token = await _login(client, "matchrecords-page@example.com")

    response = await client.get(
        "/members/me/match-records?page=0",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 422


async def test_member_match_records_locked_until_email_verified(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Constitution IV. An OAuth member is created verified even without an
    e-mail, so this only ever stops an e-mail/password registrant who has
    not clicked the verification link yet."""
    await _register(db_session, "matchrecords-unverified@example.com", verified=False)
    access_token = await _login(client, "matchrecords-unverified@example.com")

    response = await client.get(
        "/members/me/match-records", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error_code"] == "EMAIL_NOT_VERIFIED"
    assert "matches" not in body and "total_matches" not in body


async def test_line_member_without_an_email_is_not_locked_out(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """"Verified" means the identity is trusted, not that an e-mail exists:
    a LINE login that shares no e-mail creates the member already verified
    (027 research.md #6), so the lock above never applies to them — for the
    record list or for 034's dashboard."""
    result = await _complete_oauth_login(
        db_session, "line", OAuthProfile(sub="line-user-without-email", email=None)
    )
    assert result.status == "success" and result.access_token is not None
    headers = {"Authorization": f"Bearer {result.access_token}"}

    me = await client.get("/members/me", headers=headers)
    assert me.json()["email"] is None

    for path in ("/members/me/match-records", "/members/me/match-dashboard"):
        response = await client.get(path, headers=headers)
        assert response.status_code == 200, path
        assert response.json()["total_matches"] == 0

