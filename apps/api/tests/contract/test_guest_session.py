"""Contract test for GET /groups/by-guest-token/{token} per
contracts/join-api.md."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_resolve_guest_session_succeeds(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    create_response = await client.post(
        "/groups",
        json={
            "name": "Guest Session Contract Group",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = create_response.json()
    join_response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小美"}
    )
    guest_token = join_response.json()["guest_session_token"]

    response = await client.get(f"/groups/by-guest-token/{guest_token}")
    assert response.status_code == 200
    body = response.json()
    assert body["roster_entry_id"] == join_response.json()["roster_entry_id"]
    assert body["nickname"] == "小美"
    assert body["group_id"] == created["group_id"]


async def test_resolve_guest_session_unknown_token(client: AsyncClient) -> None:
    response = await client.get("/groups/by-guest-token/not-a-real-token")
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"
