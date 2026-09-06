"""Integration test: manual mode court shows "waiting for admin" -> admin
assigns players -> court immediately in_progress, no queued state ever
appears (spec US2 acceptance scenarios 1, 2)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_manual_assign_flow(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Manual Assign Flow",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿智",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    court_response = await client.post(
        f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"}
    )
    court = court_response.json()

    await db_session.execute(
        text(
            "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
            "VALUES (:id, :group_id, 'P0', 'active', false)"
        ),
        {"id": str(uuid.uuid4()), "group_id": group_id},
    )
    await db_session.commit()

    # Court starts waiting for admin assignment — no schedule call needed
    # yet, but the schedule snapshot must reflect it.
    schedule_response = await client.get(f"/groups/{group_id}/schedule", headers=headers)
    assert schedule_response.json()["courts"][0]["waiting_reason"] == "manual_assignment"
    assert schedule_response.json()["courts"][0]["current_match"] is None

    roster = await db_session.execute(
        text("SELECT id FROM roster_entries WHERE group_id = :gid ORDER BY joined_at"),
        {"gid": group_id},
    )
    ids = [str(row[0]) for row in roster.all()]
    assert len(ids) == 2

    assign_response = await client.post(
        f"/courts/{court['court_id']}/manual-assign",
        headers=headers,
        json={"participant_ids": ids, "teams": {ids[0]: "A", ids[1]: "B"}},
    )
    assert assign_response.status_code == 201
    assert assign_response.json()["status"] == "in_progress"

    final_schedule = await client.get(f"/groups/{group_id}/schedule", headers=headers)
    court_status = final_schedule.json()["courts"][0]
    assert court_status["waiting_reason"] is None
    assert court_status["current_match"]["status"] == "in_progress"
