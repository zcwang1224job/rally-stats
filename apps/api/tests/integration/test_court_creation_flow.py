"""Integration test: create court → list reflects it immediately with fresh
links/versions (spec US1 acceptance scenarios 1 and 5)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_create_court_flow(client: AsyncClient, valid_turnstile_token: str) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Court Creation Flow",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "小芳",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    empty_list = await client.get(f"/groups/{group_id}/courts", headers=headers)
    assert empty_list.json()["active_court_count"] == 0

    create_response = await client.post(
        f"/groups/{group_id}/courts", headers=headers, json={"name": "中央場"}
    )
    assert create_response.status_code == 201
    court = create_response.json()
    assert court["scoreboard_link_version"] == 0
    assert court["control_panel_link_version"] == 0
    assert court["scoreboard_token"] != court["control_panel_token"]

    list_response = await client.get(f"/groups/{group_id}/courts", headers=headers)
    body = list_response.json()
    assert body["active_court_count"] == 1
    assert body["courts"][0]["court_id"] == court["court_id"]
