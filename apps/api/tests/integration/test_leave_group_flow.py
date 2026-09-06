"""Integration test: a Guest member leaves on their own -> their guest
session token is immediately invalid, their queued match is abandoned, an
unrelated in_progress match is untouched, and no round regeneration happens
(005-member-view US4, FR-013~016)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_leave_group_converges_schedule_and_invalidates_token(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Leave Group Flow",
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
    p3 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P3"})).json()

    p0_result = await db_session.execute(
        text("SELECT id FROM roster_entries WHERE group_id = :gid AND nickname = 'P0'"),
        {"gid": group_id},
    )
    p0_id = str(p0_result.scalar_one())
    p1_id = p1["roster_entry_id"]

    # In-progress match, unrelated to the leaver.
    p2_id = p2["roster_entry_id"]
    assign_response = await client.post(
        f"/courts/{court_id}/manual-assign",
        headers=headers,
        json={"participant_ids": [p0_id, p2_id], "teams": {p0_id: "A", p2_id: "B"}},
    )
    in_progress_match_id = assign_response.json()["match_id"]

    # Hand-seed a queued match involving the leaver (P1), on no court yet.
    queued_match_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO matches (id, group_id, court_id, round_number, status, "
            "target_score, deuce_threshold, cap_score) "
            "VALUES (:id, :group_id, NULL, 1, 'queued', 21, 20, 30)"
        ),
        {"id": queued_match_id, "group_id": group_id},
    )
    for pid, team in ((p1_id, "A"), (p3["roster_entry_id"], "B")):
        await db_session.execute(
            text(
                "INSERT INTO match_participants (id, match_id, roster_entry_id, team) "
                "VALUES (:id, :match_id, :roster_entry_id, :team)"
            ),
            {
                "id": str(uuid.uuid4()),
                "match_id": queued_match_id,
                "roster_entry_id": pid,
                "team": team,
            },
        )
    await db_session.commit()

    round_before = (await client.get(f"/groups/{group_id}/schedule", headers=headers)).json()[
        "current_round_number"
    ]

    leave_response = await client.post(
        f"/groups/{group_id}/roster/{p1_id}/leave",
        json={"guest_session_token": p1["guest_session_token"]},
    )
    assert leave_response.status_code == 201
    assert leave_response.json()["status"] == "left"

    # Guest token is immediately invalid.
    schedule_after_leave = await client.get(
        f"/groups/{group_id}/member-schedule",
        params={"guest_session_token": p1["guest_session_token"]},
    )
    assert schedule_after_leave.status_code == 403
    assert schedule_after_leave.json()["error_code"] == "MEMBERSHIP_REQUIRED"

    queued_status = await db_session.execute(
        text("SELECT status FROM matches WHERE id = :id"), {"id": queued_match_id}
    )
    assert queued_status.scalar_one() == "abandoned"

    in_progress_status = await db_session.execute(
        text("SELECT status FROM matches WHERE id = :id"), {"id": in_progress_match_id}
    )
    assert in_progress_status.scalar_one() == "in_progress"

    round_after = (await client.get(f"/groups/{group_id}/schedule", headers=headers)).json()[
        "current_round_number"
    ]
    assert round_after == round_before
