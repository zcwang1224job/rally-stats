"""Integration test: multi-round flow covering candidate/bench, abandoned,
mid-tournament kick, and mid-tournament join -> the standings endpoint
correctly classifies every state (005-member-view US2, FR-005~010) as a
per-round {wins, losses, left} tally (011-round-robin-scheduling)."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import Match

pytestmark = pytest.mark.asyncio


async def test_standings_flow_all_four_states(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Standings Flow",
            "max_members": 6,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "P0",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]
    p0_guest_token = created["guest_session_token"]

    court_response = await client.post(
        f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"}
    )
    court_id = court_response.json()["court_id"]

    p1 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P1"})).json()
    p2 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P2"})).json()

    roster = await db_session.execute(
        text("SELECT id, nickname FROM roster_entries WHERE group_id = :gid"), {"gid": group_id}
    )
    id_by_nickname = {row[1]: str(row[0]) for row in roster.all()}
    p0_id, p1_id, p2_id = id_by_nickname["P0"], p1["roster_entry_id"], p2["roster_entry_id"]

    round1 = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert round1.json()["current_round_number"] == 1

    assign1 = await client.post(
        f"/courts/{court_id}/manual-assign",
        headers=headers,
        json={"participant_ids": [p0_id, p1_id], "teams": {p0_id: "A", p1_id: "B"}},
    )
    match1_id = assign1.json()["match_id"]
    end1 = await client.post(
        f"/groups/{group_id}/courts/{court_id}/matches/{match1_id}/end", headers=headers
    )
    assert end1.json()["status"] == "abandoned"

    kick_response = await client.delete(f"/groups/{group_id}/members/{p2_id}", headers=headers)
    assert kick_response.json()["status"] == "kicked"

    round2 = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert round2.json()["current_round_number"] == 2

    assign2 = await client.post(
        f"/courts/{court_id}/manual-assign",
        headers=headers,
        json={"participant_ids": [p0_id, p1_id], "teams": {p0_id: "A", p1_id: "B"}},
    )
    match2_id = assign2.json()["match_id"]
    match2_result = await db_session.execute(
        select(Match).where(Match.id == uuid.UUID(match2_id))
    )
    match2 = match2_result.scalar_one()
    match2.status = "completed"
    match2.winner_team = "A"
    match2.ended_at = datetime.now(UTC)
    await db_session.commit()

    p3 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P3"})).json()

    standings_response = await client.get(
        f"/groups/{group_id}/standings", params={"guest_session_token": p0_guest_token}
    )
    assert standings_response.status_code == 200
    body = standings_response.json()
    assert body["rounds"] == [1, 2]

    rows_by_id = {row["roster_entry_id"]: row for row in body["members"]}
    not_played = {"wins": 0, "losses": 0, "left": False}

    assert rows_by_id[p0_id]["rounds"]["1"] == not_played
    assert rows_by_id[p0_id]["rounds"]["2"] == {"wins": 1, "losses": 0, "left": False}

    assert rows_by_id[p1_id]["rounds"]["1"] == not_played
    assert rows_by_id[p1_id]["rounds"]["2"] == {"wins": 0, "losses": 1, "left": False}

    assert rows_by_id[p2_id]["current_status"] == "kicked"
    assert rows_by_id[p2_id]["rounds"]["1"] == not_played
    assert rows_by_id[p2_id]["rounds"]["2"] == {"wins": 0, "losses": 0, "left": True}

    p3_id = p3["roster_entry_id"]
    assert rows_by_id[p3_id]["rounds"]["1"] == not_played
    assert rows_by_id[p3_id]["rounds"]["2"] == not_played
