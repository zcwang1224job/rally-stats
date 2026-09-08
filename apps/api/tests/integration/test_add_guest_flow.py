"""Integration test: a manually-added guest behaves identically to a
self-joined guest — appears in the roster, gets scheduled into a match, can
resolve their own session via the existing guest-token endpoint, and can be
kicked via the existing kick endpoint (015-manual-add-guest)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_manually_added_guest_joins_rotation_and_is_kickable(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Add Guest Flow",
            "max_members": 8,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿凱",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    group_id = created["group_id"]
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "場地1"})

    add_response = await client.post(
        f"/groups/{group_id}/members", json={"nickname": "小明"}, headers=headers
    )
    assert add_response.status_code == 201
    body = add_response.json()
    roster_entry_id = body["roster_entry_id"]
    guest_session_token = body["guest_session_token"]

    schedule_before = (
        await client.get(f"/groups/{group_id}/schedule", headers=headers)
    ).json()
    entry_before = next(
        r for r in schedule_before["roster"] if r["roster_entry_id"] == roster_entry_id
    )
    assert entry_before["status"] == "active"
    assert entry_before["wait_count"] is None
    assert entry_before["currently_playing"] is False

    guest_session = await client.get(f"/groups/by-guest-token/{guest_session_token}")
    assert guest_session.status_code == 200
    assert guest_session.json()["group_id"] == group_id
    assert guest_session.json()["nickname"] == "小明"

    round_response = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert round_response.status_code == 200
    in_progress = [c for c in round_response.json()["courts"] if c["current_match"] is not None]
    assert len(in_progress) == 1
    playing_ids = {p["roster_entry_id"] for p in in_progress[0]["current_match"]["participants"]}
    assert roster_entry_id in playing_ids

    kick_response = await client.delete(
        f"/groups/{group_id}/members/{roster_entry_id}", headers=headers
    )
    assert kick_response.status_code == 200
    assert kick_response.json()["status"] == "kicked"
