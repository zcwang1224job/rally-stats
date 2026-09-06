"""Contract test for POST /groups/{group_id}/roster/{roster_entry_id}/leave
per contracts/member-view-api.md (005-member-view US4)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_leave_group_succeeds(client: AsyncClient, valid_turnstile_token: str) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Leave Group Contract",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿正",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    joined = (
        await client.post(f"/groups/{created['group_id']}/join", json={"nickname": "小美"})
    ).json()

    response = await client.post(
        f"/groups/{created['group_id']}/roster/{joined['roster_entry_id']}/leave",
        json={"guest_session_token": joined["guest_session_token"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["roster_entry_id"] == joined["roster_entry_id"]
    assert body["status"] == "left"


async def test_leave_group_by_wrong_person_returns_not_found(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Leave Group Contract 2",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿正",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    joined = (
        await client.post(f"/groups/{created['group_id']}/join", json={"nickname": "小美"})
    ).json()

    response = await client.post(
        f"/groups/{created['group_id']}/roster/{joined['roster_entry_id']}/leave",
        json={"guest_session_token": "not-the-right-token"},
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "ROSTER_ENTRY_NOT_FOUND"
