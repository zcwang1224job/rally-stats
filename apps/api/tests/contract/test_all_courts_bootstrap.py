"""Contract test for GET /groups/by-all-courts-token/{token} per
specs/002-court-management/contracts/courts-api.md."""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_all_courts_bootstrap_lists_active_courts(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "All Courts Bootstrap",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿德",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "2號場"})

    admin_view = (await client.get(f"/groups/{group_id}/admin", headers=headers)).json()
    all_courts_token = admin_view["all_courts_control_panel_token"]

    response = await client.get(f"/groups/by-all-courts-token/{all_courts_token}")
    assert response.status_code == 200
    body = response.json()
    assert body["group_id"] == group_id
    assert body["group_disbanded"] is False
    assert body["all_courts_link_version"] == 0
    assert {c["name"] for c in body["courts"]} == {"1號場", "2號場"}
    # Individual court link tokens must never leak through this endpoint.
    for court in body["courts"]:
        assert "scoreboard_token" not in court
        assert "control_panel_token" not in court


async def test_unknown_all_courts_token_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/groups/by-all-courts-token/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"
