"""Contract test for PATCH /groups/{group_id}/auto-next-round per
contracts/schedule-api.md."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group(client: AsyncClient, token: str, scheduling_mechanism: str) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": "Auto Next Round Contract",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": scheduling_mechanism,
            "creator_nickname": "阿柏",
            "turnstile_token": token,
        },
    )
    return response.json()


async def test_enable_auto_next_round(client: AsyncClient, valid_turnstile_token: str) -> None:
    created = await _create_group(client, valid_turnstile_token, "fair_rotation")
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.patch(
        f"/groups/{created['group_id']}/auto-next-round",
        headers=headers,
        json={"enabled": True},
    )
    assert response.status_code == 200
    assert response.json()["auto_next_round"] is True


async def test_enable_rejected_in_manual_mode(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token, "manual")
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.patch(
        f"/groups/{created['group_id']}/auto-next-round",
        headers=headers,
        json={"enabled": True},
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "AUTO_NEXT_ROUND_NOT_SUPPORTED_IN_MANUAL_MODE"


async def test_switching_to_manual_force_disables_auto_next_round(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token, "fair_rotation")
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    await client.patch(
        f"/groups/{created['group_id']}/auto-next-round", headers=headers, json={"enabled": True}
    )
    edit_response = await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 0, "scheduling_mechanism": "manual"},
    )
    assert edit_response.status_code == 200
    assert edit_response.json()["group"]["match_mode"] == "doubles"

    schedule_response = await client.get(f"/groups/{created['group_id']}/schedule", headers=headers)
    assert schedule_response.json()["auto_next_round"] is False
