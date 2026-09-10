"""Integration test: two courts → all-courts bootstrap lists both → deleting
one immediately reflects in the list, no link regeneration needed
(spec US3 acceptance scenarios 1, 5)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_all_courts_panel_reflects_court_changes(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "All Courts Panel Flow",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿珍",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    court_a = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "A場"})
    ).json()
    await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "B場"})

    admin_view = (await client.get(f"/groups/{group_id}/admin", headers=headers)).json()
    all_courts_token = admin_view["all_courts_control_panel_token"]

    bootstrap = (await client.get(f"/groups/by-all-courts-token/{all_courts_token}")).json()
    # 021-group-creation-defaults FR-006: every group starts with one
    # auto-created "球場一" court, on top of the 2 added here.
    assert len(bootstrap["courts"]) == 3

    await client.delete(f"/courts/{court_a['court_id']}", headers=headers)

    bootstrap_after_delete = (
        await client.get(f"/groups/by-all-courts-token/{all_courts_token}")
    ).json()
    assert len(bootstrap_after_delete["courts"]) == 2
    assert {c["name"] for c in bootstrap_after_delete["courts"]} == {"球場一", "B場"}
    # The all-courts token itself is unaffected by an individual court's deletion.
    assert bootstrap_after_delete["all_courts_link_version"] == 0
