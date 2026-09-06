"""Integration test: the general-member view's full lifecycle in one flow
per quickstart.md — nav/read-only schedule access control -> multi-round
standings (bench/abandoned/kick/won/lost all appear) -> match-records
excludes non-completed matches -> leave invalidates the Guest session
(005-member-view, all of US1-US4)."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import Match

pytestmark = pytest.mark.asyncio


async def test_member_view_full_lifecycle(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Member View Lifecycle",
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

    court_response = await client.post(
        f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"}
    )
    court_id = court_response.json()["court_id"]

    p1 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P1"})).json()
    p2 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P2"})).json()
    p1_id = p1["roster_entry_id"]
    p2_id = p2["roster_entry_id"]
    p0_id = str(
        (
            await db_session.execute(
                text("SELECT id FROM roster_entries WHERE group_id = :gid AND nickname = 'P0'"),
                {"gid": group_id},
            )
        ).scalar_one()
    )

    # US1: nav access control — no token rejected, valid Guest token works.
    no_token_response = await client.get(f"/groups/{group_id}/member-schedule")
    assert no_token_response.status_code == 403
    assert no_token_response.json()["error_code"] == "MEMBERSHIP_REQUIRED"

    schedule_response = await client.get(
        f"/groups/{group_id}/member-schedule",
        params={"guest_session_token": p1["guest_session_token"]},
    )
    assert schedule_response.status_code == 200
    assert schedule_response.json()["current_round_number"] == 1

    # Round 1: P0 vs P1, ended early (abandoned) -> both did_not_play; P2 benched.
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

    # P2 kicked after round 1 started -> "left" from round 2 onward.
    kick_response = await client.delete(f"/groups/{group_id}/members/{p2_id}", headers=headers)
    assert kick_response.json()["status"] == "kicked"

    # Round 2: P0 vs P1, completes naturally -> won/lost.
    round2 = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert round2.json()["current_round_number"] == 2

    assign2 = await client.post(
        f"/courts/{court_id}/manual-assign",
        headers=headers,
        json={"participant_ids": [p0_id, p1_id], "teams": {p0_id: "A", p1_id: "B"}},
    )
    match2_id = assign2.json()["match_id"]
    match2_result = await db_session.execute(select(Match).where(Match.id == uuid.UUID(match2_id)))
    match2 = match2_result.scalar_one()
    match2.status = "completed"
    match2.winner_team = "A"
    match2.ended_at = datetime.now(UTC)
    await db_session.commit()

    # US2: standings shows all four states.
    standings_response = await client.get(
        f"/groups/{group_id}/standings", params={"guest_session_token": p1["guest_session_token"]}
    )
    assert standings_response.status_code == 200
    standings = {m["roster_entry_id"]: m for m in standings_response.json()["members"]}

    not_played = {"wins": 0, "losses": 0, "left": False}
    assert standings[p0_id]["rounds"]["1"] == not_played
    assert standings[p0_id]["rounds"]["2"] == {"wins": 1, "losses": 0, "left": False}
    assert standings[p1_id]["rounds"]["1"] == not_played
    assert standings[p1_id]["rounds"]["2"] == {"wins": 0, "losses": 1, "left": False}
    assert standings[p2_id]["current_status"] == "kicked"
    assert standings[p2_id]["rounds"]["1"] == not_played
    assert standings[p2_id]["rounds"]["2"] == {"wins": 0, "losses": 0, "left": True}

    # US3: match-records shows only the completed round-2 match.
    records_response = await client.get(
        f"/groups/{group_id}/match-records",
        params={"guest_session_token": p1["guest_session_token"]},
    )
    assert records_response.status_code == 200
    records = records_response.json()["matches"]
    assert [m["match_id"] for m in records] == [match2_id]
    assert records[0]["winner_team"] == "A"

    # US4: P1 leaves -> Guest token immediately invalid, no round regeneration.
    leave_response = await client.post(
        f"/groups/{group_id}/roster/{p1_id}/leave",
        json={"guest_session_token": p1["guest_session_token"]},
    )
    assert leave_response.status_code == 201
    assert leave_response.json()["status"] == "left"

    post_leave_schedule = await client.get(
        f"/groups/{group_id}/member-schedule",
        params={"guest_session_token": p1["guest_session_token"]},
    )
    assert post_leave_schedule.status_code == 403
    assert post_leave_schedule.json()["error_code"] == "MEMBERSHIP_REQUIRED"

    round_after_leave = (
        await client.get(f"/groups/{group_id}/schedule", headers=headers)
    ).json()["current_round_number"]
    assert round_after_leave == 2
