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
    client: AsyncClient, session: AsyncSession, token: str
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
    court_response = await client.post(
        f"/groups/{created['group_id']}/courts", headers=headers, json={"name": "1號場"}
    )
    court = court_response.json()

    await session.execute(
        text(
            "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
            "VALUES (:id, :group_id, 'P0', 'active', false)"
        ),
        {"id": str(uuid.uuid4()), "group_id": created["group_id"]},
    )
    await session.commit()
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
