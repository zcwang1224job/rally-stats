"""Contract test for POST /groups/reauth per contracts/groups-api.md."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_reauth_with_correct_credentials_returns_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Reauth Contract",
                "max_members": 4,
                "match_mode": "doubles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "阿德",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()

    response = await client.post(
        "/groups/reauth",
        json={"group_number": created["group_number"], "admin_pin": created["admin_pin"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["group_id"] == created["group_id"]
    assert body["admin_token"]


async def test_reauth_with_wrong_pin_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/groups/reauth", json={"group_number": 999999999, "admin_pin": "000000"}
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "GROUP_ADMIN_PIN_INCORRECT"
