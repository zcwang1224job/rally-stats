"""Integration test: browse list -> verify password (with a wrong-then-right
retry) -> submit nickname -> join succeeds -> current_member_count and
RosterEntry are correct (US1)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_full_join_flow(client: AsyncClient, valid_turnstile_token: str) -> None:
    create_response = await client.post(
        "/groups",
        json={
            "name": "Full Join Flow Group",
            "password": "letmein1",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = create_response.json()
    group_id = created["group_id"]

    list_response = await client.get("/groups")
    listed = next(g for g in list_response.json()["groups"] if g["group_id"] == group_id)
    assert listed["has_password"] is True
    assert listed["current_member_count"] == 1

    wrong_password_response = await client.post(
        f"/groups/{group_id}/verify-password", json={"password": "wrong"}
    )
    assert wrong_password_response.json()["correct"] is False

    correct_password_response = await client.post(
        f"/groups/{group_id}/verify-password", json={"password": "letmein1"}
    )
    assert correct_password_response.json()["correct"] is True

    join_response = await client.post(
        f"/groups/{group_id}/join",
        json={"password": "letmein1", "nickname": "小美"},
    )
    assert join_response.status_code == 201
    body = join_response.json()
    assert body["nickname"] == "小美"
    assert body["guest_session_token"]

    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}
    admin_view = (
        await client.get(f"/groups/{group_id}/admin", headers=admin_headers)
    ).json()
    assert admin_view["group"]["current_member_count"] == 2
