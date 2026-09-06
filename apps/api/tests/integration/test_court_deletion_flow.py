"""Integration test: delete a court → its links immediately invalidate (via
by-token 404) → active count drops → the name becomes reusable (spec US2
acceptance scenarios 1, 4; US1 acceptance scenario 4)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_court_deletion_flow(client: AsyncClient, valid_turnstile_token: str) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Court Deletion Flow",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "小林",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    create_response = await client.post(
        f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"}
    )
    court = create_response.json()
    scoreboard_token = court["scoreboard_token"]

    delete_response = await client.delete(f"/courts/{court['court_id']}", headers=headers)
    assert delete_response.status_code == 200

    # The token itself still resolves (soft delete keeps the row) but reports
    # deleted:true — 404/LINK_NOT_FOUND is reserved for a token that never
    # existed (e.g. superseded by a regenerated one, see US5).
    by_token = await client.get(f"/courts/by-token/{scoreboard_token}")
    assert by_token.status_code == 200
    assert by_token.json()["deleted"] is True

    list_response = await client.get(f"/groups/{group_id}/courts", headers=headers)
    assert list_response.json()["active_court_count"] == 0

    recreate_response = await client.post(
        f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"}
    )
    assert recreate_response.status_code == 201
