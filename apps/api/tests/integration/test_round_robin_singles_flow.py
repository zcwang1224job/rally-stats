"""Integration test: singles fair_rotation produces a full round-robin
schedule and courts consume it sequentially until every match is done
(011-round-robin-scheduling quickstart.md scenario 1)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_singles_round_robin_full_flow(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Round Robin Singles Flow",
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

    court = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()

    # 4 more members (+ creator = 5) -> C(5,2) = 10 matches this round.
    for i in range(4):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()

    response = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert response.status_code == 200

    count_result = await db_session.execute(
        text("SELECT COUNT(*) FROM matches WHERE group_id = :gid AND round_number = 1"),
        {"gid": group_id},
    )
    assert count_result.scalar_one() == 10

    # Drain the whole round-robin one match at a time via the court's
    # scoreboard token; the court MUST always be able to pick up the next
    # eligible queued match until all 10 are terminal.
    ended = 0
    for _ in range(10):
        state = (
            await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
        ).json()
        current_match = state["current_match"]
        assert current_match is not None, f"court went idle after only {ended} matches ended"
        await client.post(
            f"/courts/by-token/{court['control_panel_token']}/matches/{current_match['match_id']}/end"
        )
        ended += 1

    assert ended == 10

    final_state = (await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")).json()
    assert final_state["current_match"] is None
    assert final_state["waiting_reason"] == "no_queued_match"

    status_counts = await db_session.execute(
        text(
            "SELECT status, COUNT(*) FROM matches WHERE group_id = :gid AND round_number = 1 "
            "GROUP BY status"
        ),
        {"gid": group_id},
    )
    counts = dict(status_counts.all())
    assert counts.get("abandoned", 0) == 10
    assert counts.get("queued", 0) == 0
    assert counts.get("in_progress", 0) == 0
