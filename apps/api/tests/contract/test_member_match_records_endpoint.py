"""Contract test for GET /members/me/match-records per
contracts/member-view-api.md (005-member-view US5)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register(session: AsyncSession, email: str) -> Member:
    return await register(session, email, "abc12345")


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
