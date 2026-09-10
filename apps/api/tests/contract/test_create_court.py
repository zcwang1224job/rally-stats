"""Contract test for POST /groups/{group_id}/courts and GET /groups/{group_id}/courts
per specs/002-court-management/contracts/courts-api.md."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group(client: AsyncClient, token: str) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": "Court Contract Test",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿宏",
            "turnstile_token": token,
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_create_court_returns_links_and_versions(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/courts",
        headers=headers,
        json={"name": "1號場"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "1號場"
    assert body["scoreboard_token"]
    assert body["control_panel_token"]
    assert body["scoreboard_link_version"] == 0
    assert body["control_panel_link_version"] == 0


async def test_create_court_requires_admin_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    response = await client.post(f"/groups/{created['group_id']}/courts", json={"name": "1號場"})
    assert response.status_code == 401


async def test_list_courts_reflects_active_count(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    group_id = created["group_id"]
    await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "2號場"})

    response = await client.get(f"/groups/{group_id}/courts", headers=headers)
    assert response.status_code == 200
    body = response.json()
    # 021-group-creation-defaults FR-006: every group starts with one
    # auto-created "球場一" court, on top of the 2 manually added here.
    assert body["active_court_count"] == 3
    assert {c["name"] for c in body["courts"]} == {"球場一", "1號場", "2號場"}
