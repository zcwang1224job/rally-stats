"""Contract test for GET /groups/{group_id}/standings per
contracts/member-view-api.md (005-member-view US2)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member

pytestmark = pytest.mark.asyncio


async def _create_group_and_join(client: AsyncClient, token: str) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Standings Contract",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿正",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    join_response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小美"}
    )
    return created, join_response.json()


async def _join_as_logged_in_member(
    client: AsyncClient, db_session: AsyncSession, group_id: str, email: str, turnstile_token: str
) -> str:
    """Registers, verifies, logs in, sets a nickname, and joins `group_id`
    as a Member (not a Guest) — returns the Bearer access token."""
    await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": turnstile_token,
        },
    )
    result = await db_session.execute(select(Member).where(Member.email == email))
    member = result.scalar_one()
    member.verification_status = "verified"
    await db_session.commit()

    login_response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    access_token = str(login_response.json()["access_token"])
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.patch("/members/me/nickname", headers=headers, json={"nickname": "會員小張"})
    join_response = await client.post(f"/groups/{group_id}/join", headers=headers, json={})
    assert join_response.status_code == 201
    return access_token


async def test_standings_with_guest_token_succeeds(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created, joined = await _create_group_and_join(client, valid_turnstile_token)

    response = await client.get(
        f"/groups/{created['group_id']}/standings",
        params={"guest_session_token": joined["guest_session_token"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_round_number"] == 1
    assert body["rounds"] == []  # round 1 hasn't happened yet (research.md #2)
    assert len(body["members"]) == 2  # creator + one joined guest
    assert all(member["current_status"] == "active" for member in body["members"])


async def test_standings_without_token_returns_membership_required(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created, _joined = await _create_group_and_join(client, valid_turnstile_token)

    response = await client.get(f"/groups/{created['group_id']}/standings")
    assert response.status_code == 403
    assert response.json()["error_code"] == "MEMBERSHIP_REQUIRED"


async def test_standings_with_logged_in_member_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, _joined = await _create_group_and_join(client, valid_turnstile_token)
    access_token = await _join_as_logged_in_member(
        client, db_session, created["group_id"], "standings-member-auth@example.com",
        valid_turnstile_token,
    )

    response = await client.get(
        f"/groups/{created['group_id']}/standings",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert len(response.json()["members"]) == 3  # creator + guest + this member
