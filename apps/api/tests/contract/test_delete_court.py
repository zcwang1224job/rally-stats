"""Contract test for DELETE /courts/{court_id} per contracts/courts-api.md."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group_with_court(client: AsyncClient, token: str) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Delete Court Contract",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿泰",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    court_response = await client.post(
        f"/groups/{created['group_id']}/courts", headers=headers, json={"name": "1號場"}
    )
    return created, court_response.json()


async def test_delete_court_succeeds(client: AsyncClient, valid_turnstile_token: str) -> None:
    created, court = await _create_group_with_court(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.delete(f"/courts/{court['court_id']}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] is True
    assert body["had_active_match"] is False


async def test_deleting_twice_returns_court_deleted(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_court(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    await client.delete(f"/courts/{court['court_id']}", headers=headers)
    second = await client.delete(f"/courts/{court['court_id']}", headers=headers)
    assert second.status_code == 409
    assert second.json()["error_code"] == "COURT_DELETED"


async def test_delete_court_requires_admin_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_court(client, valid_turnstile_token)
    response = await client.delete(f"/courts/{court['court_id']}")
    assert response.status_code == 401
