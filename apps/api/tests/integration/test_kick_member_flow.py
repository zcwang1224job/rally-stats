"""Integration test: kick a member mid-Round while they're involved in both a
queued and (a different member's) in_progress match -> queued match involving
them is abandoned, in_progress match is untouched, no round regeneration
happens (FR-039/040/041)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_kick_member_converges_schedule_without_regenerating_round(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Kick Member Flow",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿修",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    for i in range(2):
        await client.post(
            f"/groups/{group_id}/courts", headers=headers, json={"name": f"場地{i}"}
        )

    # Creator + 7 seeded = 8 -> exactly 2 courts full, no queued leftover from
    # generation itself; instead we hand-seed one extra queued match below so
    # there's something deterministic to kick a member out of.
    for i in range(7):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()

    round_response = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert round_response.status_code == 200
    body = round_response.json()
    in_progress_courts = [c for c in body["courts"] if c["current_match"] is not None]
    assert len(in_progress_courts) == 2

    in_progress_participant_id = in_progress_courts[0]["current_match"]["participants"][0][
        "roster_entry_id"
    ]

    # Hand-seed one extra queued match in the current round so there is a
    # deterministic queued match to converge on kick.
    extra_a = str(uuid.uuid4())
    extra_b = str(uuid.uuid4())
    for pid in (extra_a, extra_b):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, 'extra', 'active', false)"
            ),
            {"id": pid, "group_id": group_id},
        )
    match_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO matches (id, group_id, court_id, round_number, status, "
            "target_score, deuce_threshold, cap_score) "
            "VALUES (:id, :group_id, NULL, :round_number, 'queued', 21, 20, 30)"
        ),
        {"id": match_id, "group_id": group_id, "round_number": body["current_round_number"]},
    )
    for pid, team in ((extra_a, "A"), (extra_b, "B")):
        await db_session.execute(
            text(
                "INSERT INTO match_participants (id, match_id, roster_entry_id, team) "
                "VALUES (:id, :match_id, :roster_entry_id, :team)"
            ),
            {"id": str(uuid.uuid4()), "match_id": match_id, "roster_entry_id": pid, "team": team},
        )
    await db_session.commit()

    kick_response = await client.delete(
        f"/groups/{group_id}/members/{extra_a}", headers=headers
    )
    assert kick_response.status_code == 200
    assert kick_response.json()["status"] == "kicked"

    queued_status = await db_session.execute(
        text("SELECT status FROM matches WHERE id = :id"), {"id": match_id}
    )
    assert queued_status.scalar_one() == "abandoned"

    # The in-progress match and the group's round number are unaffected.
    schedule_after = (await client.get(f"/groups/{group_id}/schedule", headers=headers)).json()
    assert schedule_after["current_round_number"] == body["current_round_number"]
    still_in_progress = [c for c in schedule_after["courts"] if c["current_match"] is not None]
    assert len(still_in_progress) == 2
    all_still_playing = {
        p["roster_entry_id"] for c in still_in_progress for p in c["current_match"]["participants"]
    }
    assert in_progress_participant_id in all_still_playing
