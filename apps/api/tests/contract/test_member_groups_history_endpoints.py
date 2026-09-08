"""Contract tests for 014-member-groups-history, per
specs/014-member-groups-history/contracts/member-groups-history-api.md."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register_and_verify(session: AsyncSession, email: str, nickname: str) -> None:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    return str(response.json()["access_token"])


async def _create_member_group(
    client: AsyncClient, access_token: str, turnstile_token: str, name: str
) -> dict:
    response = await client.post(
        "/groups",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "name": name,
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "turnstile_token": turnstile_token,
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_my_groups_includes_is_creator_and_member_status(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    await _register_and_verify(db_session, "history-c-a1@example.com", "團長")
    await _register_and_verify(db_session, "history-c-b1@example.com", "團員")
    a_token = await _login(client, "history-c-a1@example.com")
    b_token = await _login(client, "history-c-b1@example.com")
    group = await _create_member_group(
        client, a_token, valid_turnstile_token, "History Contract Group 1"
    )
    joined = await client.post(
        f"/groups/{group['group_id']}/join",
        headers={"Authorization": f"Bearer {b_token}"},
        json={},
    )
    assert joined.status_code == 201

    a_groups = (
        await client.get("/members/me/groups", headers={"Authorization": f"Bearer {a_token}"})
    ).json()["groups"]
    assert a_groups[0]["is_creator"] is True
    assert a_groups[0]["member_status"] == "active"

    b_groups = (
        await client.get("/members/me/groups", headers={"Authorization": f"Bearer {b_token}"})
    ).json()["groups"]
    assert b_groups[0]["is_creator"] is False
    assert b_groups[0]["member_status"] == "active"


async def test_group_history_endpoint_success_and_empty_state(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    await _register_and_verify(db_session, "history-c-a2@example.com", "團長2")
    a_token = await _login(client, "history-c-a2@example.com")
    group = await _create_member_group(
        client, a_token, valid_turnstile_token, "History Contract Group 2"
    )

    response = await client.get(
        f"/members/me/groups/{group['group_id']}/history",
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["group_name"] == "History Contract Group 2"
    assert body["matches"] == []
    assert body["my_stats"]["total_matches"] == 0
    assert body["my_stats"]["win_rate"] == 0.0


async def test_group_history_rejects_member_who_was_never_in_the_group(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    await _register_and_verify(db_session, "history-c-a3@example.com", "團長3")
    await _register_and_verify(db_session, "history-c-c3@example.com", "陌生人")
    a_token = await _login(client, "history-c-a3@example.com")
    c_token = await _login(client, "history-c-c3@example.com")
    group = await _create_member_group(
        client, a_token, valid_turnstile_token, "History Contract Group 3"
    )

    response = await client.get(
        f"/members/me/groups/{group['group_id']}/history",
        headers={"Authorization": f"Bearer {c_token}"},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "GROUP_MEMBERSHIP_NEVER_HELD"


async def test_group_history_returns_group_not_found_for_unknown_group(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "history-c-a4@example.com", "團長4")
    a_token = await _login(client, "history-c-a4@example.com")

    response = await client.get(
        "/members/me/groups/00000000-0000-0000-0000-000000000000/history",
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "GROUP_NOT_FOUND"


async def test_group_history_requires_login(client: AsyncClient) -> None:
    response = await client.get(
        "/members/me/groups/00000000-0000-0000-0000-000000000000/history"
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "MEMBER_TOKEN_INVALID"
