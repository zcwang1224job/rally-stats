"""Contract test for GET /groups per contracts/group-list-api.md."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group(
    client: AsyncClient, valid_turnstile_token: str, name: str = "List Test Group"
) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": name,
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    return response.json()


async def test_list_groups_returns_active_groups(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    await _create_group(client, valid_turnstile_token, "列表可見團")

    response = await client.get("/groups")
    assert response.status_code == 200
    body = response.json()
    assert any(g["name"] == "列表可見團" for g in body["groups"])
    assert body["page"] == 1


async def test_list_groups_excludes_disbanded(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token, "即將解散團")
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.post(f"/groups/{created['group_id']}/disband", headers=headers)

    response = await client.get("/groups")
    assert response.status_code == 200
    names = [g["name"] for g in response.json()["groups"]]
    assert "即將解散團" not in names


async def test_list_groups_joined_by_me_is_null_when_unauthenticated(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    await _create_group(client, valid_turnstile_token, "未登入檢視團")

    response = await client.get("/groups")
    assert response.status_code == 200
    item = next(g for g in response.json()["groups"] if g["name"] == "未登入檢視團")
    assert item["joined_by_me"] is None
