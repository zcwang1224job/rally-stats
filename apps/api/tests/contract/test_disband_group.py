"""Contract test for POST /groups/{id}/disband per contracts/groups-api.md."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group(client: AsyncClient, token: str) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": "Disband Contract Test",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "小美",
            "turnstile_token": token,
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_disband_requires_admin_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    response = await client.post(f"/groups/{created['group_id']}/disband")
    assert response.status_code == 401


async def test_disband_succeeds_and_status_becomes_disbanded(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(f"/groups/{created['group_id']}/disband", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "disbanded"

    public = await client.get(f"/groups/{created['group_id']}")
    assert public.json()["status"] == "disbanded"
