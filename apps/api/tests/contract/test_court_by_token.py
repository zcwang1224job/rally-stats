"""Contract test for GET /courts/by-token/{token} per contracts/courts-api.md."""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group_with_court(client: AsyncClient, token: str) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Court By Token Contract",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿豪",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    court_response = await client.post(
        f"/groups/{created['group_id']}/courts", headers=headers, json={"name": "1號場"}
    )
    return created, court_response.json()


async def test_by_token_resolves_scoreboard_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_court(client, valid_turnstile_token)

    response = await client.get(f"/courts/by-token/{court['scoreboard_token']}")
    assert response.status_code == 200
    body = response.json()
    assert body["court_id"] == court["court_id"]
    assert body["group_id"] == created["group_id"]
    assert body["link_type"] == "scoreboard"
    assert body["link_version"] == 0
    assert body["deleted"] is False
    assert body["group_disbanded"] is False


async def test_by_token_resolves_control_panel_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_court(client, valid_turnstile_token)

    response = await client.get(f"/courts/by-token/{court['control_panel_token']}")
    assert response.status_code == 200
    assert response.json()["link_type"] == "control_panel"


async def test_by_token_unknown_token_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/courts/by-token/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"


async def test_by_token_reports_group_disbanded(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_court(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.post(f"/groups/{created['group_id']}/disband", headers=headers)

    response = await client.get(f"/courts/by-token/{court['scoreboard_token']}")
    assert response.status_code == 200
    assert response.json()["group_disbanded"] is True
