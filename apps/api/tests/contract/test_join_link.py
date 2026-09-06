"""Contract test for GET /join/{join_link_token} per contracts/join-api.md."""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group(
    client: AsyncClient, valid_turnstile_token: str, **overrides: object
) -> dict:
    payload = {
        "name": "Join Link Contract Group",
        "max_members": 8,
        "match_mode": "doubles",
        "scheduling_mechanism": "manual",
        "creator_nickname": "阿明",
        "turnstile_token": valid_turnstile_token,
    }
    payload.update(overrides)
    response = await client.post("/groups", json=payload)
    return response.json()


async def test_resolve_join_link_succeeds(client: AsyncClient, valid_turnstile_token: str) -> None:
    created = await _create_group(client, valid_turnstile_token)
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}
    admin_view = (
        await client.get(f"/groups/{created['group_id']}/admin", headers=admin_headers)
    ).json()

    response = await client.get(f"/join/{admin_view['join_link_token']}")
    assert response.status_code == 200
    body = response.json()
    assert body["group_id"] == created["group_id"]
    assert body["already_joined"] is False
    assert body["status"] == "active"


async def test_resolve_join_link_unknown_token(client: AsyncClient) -> None:
    response = await client.get(f"/join/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"


async def test_resolve_join_link_disbanded_group_returns_200_with_status(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}
    admin_view = (
        await client.get(f"/groups/{created['group_id']}/admin", headers=admin_headers)
    ).json()
    await client.post(f"/groups/{created['group_id']}/disband", headers=admin_headers)

    response = await client.get(f"/join/{admin_view['join_link_token']}")
    assert response.status_code == 200
    assert response.json()["status"] == "disbanded"


async def test_resolve_join_link_full_group_returns_200_with_counts(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(
        client, valid_turnstile_token, max_members=2, match_mode="singles"
    )
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}
    admin_view = (
        await client.get(f"/groups/{created['group_id']}/admin", headers=admin_headers)
    ).json()
    await client.post(f"/groups/{created['group_id']}/join", json={"nickname": "小美"})

    response = await client.get(f"/join/{admin_view['join_link_token']}")
    assert response.status_code == 200
    body = response.json()
    assert body["current_member_count"] == body["max_members"] == 2
