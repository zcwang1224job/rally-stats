"""Integration test: 016-match-score-timeline — plays a real match to
completion via the control-panel scoring endpoint (the same write path
production traffic uses) and confirms both new detail endpoints agree on
the resulting event log (plan.md Testing commitment / tasks.md T003a);
plus the "none" and "partial" record_completeness states for matches whose
score_events don't fully cover the match (tasks.md T023)."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant, ScoreEvent

pytestmark = pytest.mark.asyncio


async def _create_group_with_active_match(
    client: AsyncClient,
    session: AsyncSession,
    token: str,
    *,
    detailed_scoring_enabled: bool = False,
) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Score Timeline Flow",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "scoring_mode": "custom",
            "custom_scoring": {"target_score": 3, "deuce_threshold": 2, "cap_score": 5},
            "creator_nickname": "阿翔",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    # 021-group-creation-defaults FR-006: the group already has one
    # auto-created "球場一" court — use that instead of adding a second one,
    # so round generation has exactly one court to assign this test's single
    # match to (a second court would otherwise compete for it).
    courts_response = await client.get(f"/groups/{created['group_id']}/courts", headers=headers)
    court = courts_response.json()["courts"][0]

    await session.execute(
        text(
            "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
            "VALUES (:id, :group_id, 'P0', 'active', false)"
        ),
        {"id": str(uuid.uuid4()), "group_id": created["group_id"]},
    )
    if detailed_scoring_enabled:
        # 032-match-record-scoring-stats: MUST be set BEFORE next-round pulls
        # a match onto the court — matches.detailed_scoring_enabled is a
        # snapshot taken at creation time (031-shot-placement-scoring).
        await session.execute(
            text("UPDATE groups SET detailed_scoring_enabled = true WHERE id = :id"),
            {"id": created["group_id"]},
        )
    await session.commit()
    session.expire_all()
    await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)

    return created, court


async def _get_match_id(client: AsyncClient, court: dict) -> str:
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    match_id: str = state.json()["current_match"]["match_id"]
    return match_id


async def test_full_flow_both_endpoints_report_complete_and_agree(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    # Play out a real deuce-ish sequence: +1 A, +1 B, -1 A (correction),
    # +1 A, +1 A, +1 A (A reaches target_score=3, natural finish).
    sequence = [("A", 1), ("B", 1), ("A", -1), ("A", 1), ("A", 1), ("A", 1)]
    for side, delta in sequence:
        response = await client.post(
            f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
            json={"side": side, "delta": delta},
        )
        assert response.status_code == 200

    guest_join = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "旁觀者"}
    )
    guest_token = guest_join.json()["guest_session_token"]

    group_scoped = await client.get(
        f"/groups/{created['group_id']}/match-records/{match_id}",
        params={"guest_session_token": guest_token},
    )
    assert group_scoped.status_code == 200
    group_body = group_scoped.json()

    assert group_body["record_completeness"] == "complete"
    assert len(group_body["events"]) == len(sequence)
    assert [(e["side"], e["delta"]) for e in group_body["events"]] == sequence
    assert group_body["score_a"] == 3
    assert group_body["score_b"] == 1
    assert group_body["winner_team"] == "A"
    # elapsed_seconds strictly non-decreasing (chronological order preserved).
    elapsed = [e["elapsed_seconds"] for e in group_body["events"]]
    assert elapsed == sorted(elapsed)


async def test_no_score_events_yields_none_completeness(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """Simulates a match completed before this feature shipped: a
    `completed` Match row with zero ScoreEvent rows (FR-006)."""
    group = Group(
        name="Pre-Feature Match",
        max_members=4,
        match_mode="singles",
        scheduling_mechanism="manual",
        current_member_count=2,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    a = RosterEntry(group_id=group.id, nickname="舊資料A", status="active")
    b = RosterEntry(group_id=group.id, nickname="舊資料B", status="active")
    db_session.add_all([a, b])
    await db_session.commit()
    await db_session.refresh(a)
    await db_session.refresh(b)

    now = datetime.now(UTC)
    match = Match(
        group_id=group.id,
        court_id=None,
        round_number=1,
        status="completed",
        winner_team="A",
        score_a=21,
        score_b=18,
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
        started_at=now,
        ended_at=now,
    )
    db_session.add(match)
    await db_session.flush()
    db_session.add(MatchParticipant(match_id=match.id, roster_entry_id=a.id, team="A"))
    db_session.add(MatchParticipant(match_id=match.id, roster_entry_id=b.id, team="B"))
    await db_session.commit()

    guest_join = await client.post(f"/groups/{group.id}/join", json={"nickname": "旁觀者"})
    guest_token = guest_join.json()["guest_session_token"]

    response = await client.get(
        f"/groups/{group.id}/match-records/{match.id}",
        params={"guest_session_token": guest_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["record_completeness"] == "none"
    assert body["events"] == []
    assert body["score_a"] == 21
    assert body["score_b"] == 18


async def test_shot_placement_detail_and_player_stats_agree_across_entry_points(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """032-match-record-scoring-stats (quickstart.md scenarios 6/9): the
    group-scoped entry point and the member entry point both funnel through
    the same `build_match_record_detail()` — this confirms they report
    identical `events[].detail`/`player_stats` for the same match, without
    either endpoint needing its own special-cased logic."""
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token, detailed_scoring_enabled=True
    )
    match_id = await _get_match_id(client, court)
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    team_a_id = next(
        p["roster_entry_id"]
        for p in state.json()["current_match"]["participants"]
        if p["team"] == "A"
    )
    team_b_id = next(
        p["roster_entry_id"]
        for p in state.json()["current_match"]["participants"]
        if p["team"] == "B"
    )

    # Point 1: full detail. Point 2: skipped. Point 3: only scoring player.
    score_1 = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )
    await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": score_1.json()["score_event_id"],
            "roster_entry_id": team_a_id,
            "losing_roster_entry_id": team_b_id,
            "landing_x": 0.62,
            "landing_y": 0.18,
        },
    )
    await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )
    score_3 = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )
    await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json={"score_event_id": score_3.json()["score_event_id"], "roster_entry_id": team_a_id},
    )

    # Group-scoped entry point (Guest viewer).
    guest_join = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "旁觀者"}
    )
    guest_token = guest_join.json()["guest_session_token"]
    group_scoped = await client.get(
        f"/groups/{created['group_id']}/match-records/{match_id}",
        params={"guest_session_token": guest_token},
    )
    assert group_scoped.status_code == 200
    group_body = group_scoped.json()

    # Member entry point — a logged-in member who joined the SAME group
    # (but wasn't a participant in this specific match; the member endpoint
    # only requires ever having been a roster entry in the group, not in
    # this match) hitting the /members/me/... variant instead.
    await client.post(
        "/auth/register",
        json={
            "email": "timeline-shotplacement@example.com",
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": "unused",
        },
    )
    await db_session.execute(
        text(
            "UPDATE members SET verification_status = 'verified' "
            "WHERE email = 'timeline-shotplacement@example.com'"
        ),
    )
    await db_session.commit()
    db_session.expire_all()
    login = await client.post(
        "/auth/login",
        json={"email": "timeline-shotplacement@example.com", "password": "abc12345"},
    )
    access_token = login.json()["access_token"]
    member_headers = {"Authorization": f"Bearer {access_token}"}
    await client.patch(
        "/members/me/nickname", headers=member_headers, json={"nickname": "旁觀會員"}
    )
    join_resp = await client.post(
        f"/groups/{created['group_id']}/join", headers=member_headers, json={}
    )
    assert join_resp.status_code == 201, join_resp.text

    member_scoped = await client.get(
        f"/members/me/match-records/{match_id}", headers=member_headers
    )
    assert member_scoped.status_code == 200
    member_body = member_scoped.json()

    assert member_body["events"] == group_body["events"]
    assert member_body["player_stats"] == group_body["player_stats"]
    # Sanity-check the actual content, not just that the two agree with
    # each other (they could both agree on the WRONG thing).
    assert group_body["events"][0]["detail"]["scoring_roster_entry_id"] == team_a_id
    assert group_body["events"][0]["detail"]["losing_roster_entry_id"] == team_b_id
    assert group_body["events"][1]["detail"] is None
    assert group_body["events"][2]["detail"]["scoring_roster_entry_id"] == team_a_id
    assert group_body["events"][2]["detail"]["losing_roster_entry_id"] is None
    stats_by_id = {s["roster_entry_id"]: s for s in group_body["player_stats"]}
    assert stats_by_id[team_a_id]["scored_count"] == 2
    assert stats_by_id[team_b_id]["fault_count"] == 1


async def test_only_trailing_score_events_yields_partial_completeness(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """Simulates a match that started before this feature shipped and
    completed after: only the tail end of the scoring was recorded
    (FR-006a). Built by playing a real match, then deleting its earliest
    events so the remaining first event's score isn't 1:0/0:1."""
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    for _ in range(3):
        response = await client.post(
            f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
            json={"side": "A", "delta": 1},
        )
        assert response.status_code == 200

    events_result = await db_session.execute(
        select(ScoreEvent)
        .where(ScoreEvent.match_id == uuid.UUID(match_id))
        .order_by(ScoreEvent.created_at)
    )
    events = list(events_result.scalars())
    assert len(events) == 3
    # Delete the earliest event so the earliest surviving one shows 2:0,
    # not 1:0 — proof that recording started mid-match.
    await db_session.delete(events[0])
    await db_session.commit()

    guest_join = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "旁觀者"}
    )
    guest_token = guest_join.json()["guest_session_token"]

    response = await client.get(
        f"/groups/{created['group_id']}/match-records/{match_id}",
        params={"guest_session_token": guest_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["record_completeness"] == "partial"
    assert len(body["events"]) == 2
    assert body["events"][0]["score_a"] == 2
    # Final score is still the real final score even though the record is
    # partial — only the beginning was missed, never the end.
    assert body["score_a"] == 3
