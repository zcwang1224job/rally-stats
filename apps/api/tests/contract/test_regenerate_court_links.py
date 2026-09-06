"""Contract test for POST /courts/{court_id}/regenerate-scoreboard-link and
regenerate-control-panel-link per contracts/courts-api.md."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group_with_court(client: AsyncClient, token: str) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Regen Court Links Contract",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿翔",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    court_response = await client.post(
        f"/groups/{created['group_id']}/courts", headers=headers, json={"name": "1號場"}
    )
    return created, court_response.json()


async def test_regenerate_scoreboard_link_succeeds(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_court(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/courts/{court['court_id']}/regenerate-scoreboard-link",
        headers=headers,
        json={"expected_version": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scoreboard_link_version"] == 1
    assert body["scoreboard_token"] != court["scoreboard_token"]


async def test_regenerate_control_panel_link_succeeds(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_court(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/courts/{court['court_id']}/regenerate-control-panel-link",
        headers=headers,
        json={"expected_version": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["control_panel_link_version"] == 1
    assert body["control_panel_token"] != court["control_panel_token"]


async def test_regenerate_link_stale_version_returns_409(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_court(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/courts/{court['court_id']}/regenerate-scoreboard-link",
        headers=headers,
        json={"expected_version": 99},
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "VERSION_CONFLICT"


async def test_regenerate_link_on_deleted_court_returns_court_deleted(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_court(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.delete(f"/courts/{court['court_id']}", headers=headers)

    response = await client.post(
        f"/courts/{court['court_id']}/regenerate-scoreboard-link",
        headers=headers,
        json={"expected_version": 0},
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "COURT_DELETED"
