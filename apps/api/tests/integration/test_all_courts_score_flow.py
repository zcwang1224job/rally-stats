"""Integration test: 全部場地控制板對某場地按 +1 → 該場地自己的
control_panel_token 控制板與對應計分板皆同步更新一致（US5 acceptance
scenario 4, FR-001）."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_all_courts_score_reflected_on_single_court_links(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "All Courts Sync Flow",
                "max_members": 8,
                "match_mode": "singles",
                "scheduling_mechanism": "fair_rotation",
                "creator_nickname": "阿源",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    court1 = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()
    court2 = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "2號場"})
    ).json()

    for i in range(7):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()
    await client.post(f"/groups/{group_id}/next-round", headers=headers)

    admin_view = (await client.get(f"/groups/{group_id}/admin", headers=headers)).json()
    all_courts_token = admin_view["all_courts_control_panel_token"]

    all_courts_state = (
        await client.get(f"/groups/by-all-courts-token/{all_courts_token}/state")
    ).json()
    match1_id = next(
        c["current_match"]["match_id"]
        for c in all_courts_state["courts"]
        if c["court_id"] == court1["court_id"]
    )

    # +1 via the all-courts panel.
    result = await client.post(
        f"/groups/by-all-courts-token/{all_courts_token}/courts/{court1['court_id']}/"
        f"matches/{match1_id}/score",
        json={"side": "A", "delta": 1},
    )
    assert result.json()["applied"] is True

    # Court 1's own single-court links (scoreboard AND control panel) both
    # reflect the change; court 2 is untouched.
    single_scoreboard = (
        await client.get(f"/courts/by-token/{court1['scoreboard_token']}/state")
    ).json()
    single_control = (
        await client.get(f"/courts/by-token/{court1['control_panel_token']}/state")
    ).json()
    assert single_scoreboard["current_match"]["score_a"] == 1
    assert single_control["current_match"]["score_a"] == 1

    court2_state = (
        await client.get(f"/courts/by-token/{court2['scoreboard_token']}/state")
    ).json()
    assert court2_state["current_match"]["score_a"] == 0

    # And the all-courts state itself reflects the change too.
    refreshed_all_courts = (
        await client.get(f"/groups/by-all-courts-token/{all_courts_token}/state")
    ).json()
    court1_in_all = next(
        c for c in refreshed_all_courts["courts"] if c["court_id"] == court1["court_id"]
    )
    assert court1_in_all["current_match"]["score_a"] == 1
