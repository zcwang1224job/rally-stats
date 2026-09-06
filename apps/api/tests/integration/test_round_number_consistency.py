"""Integration test: 同團兩場地同時進行同一輪，皆顯示相同 round_number，
直到該輪賽程表消耗完畢（管理員手動觸發 Next Round）為止（US3 acceptance
scenario 1, FR-002）."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_two_courts_show_same_round_number_until_next_round(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Round Number Consistency",
            "max_members": 8,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿宏",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    group_id = created["group_id"]
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

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

    state1 = (await client.get(f"/courts/by-token/{court1['scoreboard_token']}/state")).json()
    state2 = (await client.get(f"/courts/by-token/{court2['scoreboard_token']}/state")).json()
    assert state1["round_number"] == state2["round_number"] == 1

    control1 = (await client.get(f"/courts/by-token/{court1['control_panel_token']}/state")).json()
    control2 = (await client.get(f"/courts/by-token/{court2['control_panel_token']}/state")).json()
    assert control1["round_number"] == control2["round_number"] == 1

    # Court 1's match ends naturally — round_number for BOTH courts is
    # unchanged until the round is consumed / admin triggers Next Round.
    match1_id = state1["current_match"]["match_id"]
    await client.post(
        f"/courts/by-token/{court1['control_panel_token']}/matches/{match1_id}/end"
    )
    after1 = (await client.get(f"/courts/by-token/{court1['scoreboard_token']}/state")).json()
    after2 = (await client.get(f"/courts/by-token/{court2['scoreboard_token']}/state")).json()
    assert after1["round_number"] == 1
    assert after2["round_number"] == 1

    # Admin manually triggers Next Round — both courts advance together.
    await client.post(f"/groups/{group_id}/next-round", headers=headers)
    round3_1 = (await client.get(f"/courts/by-token/{court1['scoreboard_token']}/state")).json()
    round3_2 = (await client.get(f"/courts/by-token/{court2['scoreboard_token']}/state")).json()
    assert round3_1["round_number"] == round3_2["round_number"] == 2
