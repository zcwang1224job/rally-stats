"""Unit test: apply_score_delta() 原子防呆（FR-005/006/006a/007）與達標
後之終態轉換 + advance_court_after_match_ends hook 呼叫（research.md #5/#6）.

030-score-serve-record FR-001/FR-004: also covers that a `+1` creates a
matching `ScoreServeRecord` and a `-1` MUST NOT (Clarifications 2026-09-15)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import ScoreEvent, ScoreServeRecord, ShotPlacementRecord
from app.domains.schedule.service import (
    apply_score_delta,
    attach_shot_placement,
    create_match_with_participants,
)

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Apply Score Delta Test",
        "max_members": 4,
        "match_mode": "singles",
        "scheduling_mechanism": "fair_rotation",
        "current_member_count": 1,
        "status": "active",
        "admin_pin_hash": hash_admin_pin("111111"),
        "target_score": 21,
        "deuce_threshold": 20,
        "cap_score": 30,
    }
    defaults.update(overrides)
    group = Group(**defaults)  # type: ignore[arg-type]
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_court(session: AsyncSession, group: Group) -> Court:
    court = Court(group_id=group.id, name="1號場")
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def _make_roster_entry(session: AsyncSession, group: Group) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname="P", status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def test_plus_one_increments_score(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    result = await apply_score_delta(db_session, court, match.id, "A", 1)

    assert result.applied is True
    assert result.score_a == 1
    assert result.score_b == 0
    assert result.status == "in_progress"


async def test_minus_one_rejected_at_zero(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    result = await apply_score_delta(db_session, court, match.id, "A", -1)

    assert result.applied is False
    assert result.score_a == 0


@pytest.mark.parametrize("terminal_status", ["completed", "abandoned"])
async def test_terminal_match_rejects_plus_one(
    db_session: AsyncSession, terminal_status: str
) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status=terminal_status,
        team_a=[p1.id], team_b=[p2.id],
    )
    match.score_a = 10
    await db_session.commit()

    result = await apply_score_delta(db_session, court, match.id, "A", 1)

    assert result.applied is False
    assert result.score_a == 10
    assert result.status == terminal_status


async def test_reaching_target_completes_match_and_advances_court(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, target_score=3, deuce_threshold=2, cap_score=5)
    court = await _make_court(db_session, group)
    p1, p2, p3, p4 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    queued = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p3.id], team_b=[p4.id],
    )
    match.score_a = 2
    await db_session.commit()

    result = await apply_score_delta(db_session, court, match.id, "A", 1)

    assert result.applied is True
    assert result.status == "completed"
    assert result.winner_team == "A"
    assert result.score_a == 3

    await db_session.refresh(court)
    await db_session.refresh(queued)
    assert queued.status == "in_progress"
    assert queued.court_id == court.id


async def test_applied_delta_records_score_event(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    await apply_score_delta(db_session, court, match.id, "A", 1, source="admin")
    await apply_score_delta(db_session, court, match.id, "B", 1)

    events = (
        (
            await db_session.execute(
                select(ScoreEvent)
                .where(ScoreEvent.match_id == match.id)
                .order_by(ScoreEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    assert [(e.side, e.delta, e.score_a, e.score_b, e.source) for e in events] == [
        ("A", 1, 1, 0, "admin"),
        ("B", 1, 1, 1, "control_panel"),
    ]
    assert all(e.group_id == group.id for e in events)


async def test_rejected_delta_records_no_score_event(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    result = await apply_score_delta(db_session, court, match.id, "A", -1)

    assert result.applied is False
    count = (
        await db_session.execute(select(ScoreEvent).where(ScoreEvent.match_id == match.id))
    ).scalars().all()
    assert count == []


# --- 030-score-serve-record: +1 creates a ScoreServeRecord, -1 does not -----


async def test_plus_one_creates_matching_score_serve_record(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, match_mode="doubles")
    court = await _make_court(db_session, group)
    a1, a2, b1, b2 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[a1.id, a2.id], team_b=[b1.id, b2.id],
    )
    await db_session.commit()
    serving_team = match.serving_team
    server_before = (
        match.team_a_reference_server_id
        if serving_team == "A"
        else match.team_b_reference_server_id
    )

    await apply_score_delta(db_session, court, match.id, serving_team, 1)

    events = (
        await db_session.execute(select(ScoreEvent).where(ScoreEvent.match_id == match.id))
    ).scalars().all()
    assert len(events) == 1
    records = (
        await db_session.execute(
            select(ScoreServeRecord).where(ScoreServeRecord.match_id == match.id)
        )
    ).scalars().all()
    assert len(records) == 1
    record = records[0]
    assert record.score_event_id == events[0].id
    assert record.group_id == group.id
    # Same team kept serving (no side-out) -> same server as before this point.
    assert record.server_roster_entry_id == server_before
    assert record.server_team == serving_team
    assert record.team_a_right_roster_entry_id is not None
    assert record.team_a_left_roster_entry_id is not None
    assert record.team_b_right_roster_entry_id is not None
    assert record.team_b_left_roster_entry_id is not None


async def test_minus_one_does_not_create_score_serve_record_or_touch_serve_state(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, match_mode="doubles")
    court = await _make_court(db_session, group)
    a1, a2, b1, b2 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[a1.id, a2.id], team_b=[b1.id, b2.id],
    )
    await db_session.commit()
    serving_team_before = match.serving_team
    team_a_ref_before = match.team_a_reference_server_id
    team_b_ref_before = match.team_b_reference_server_id

    await apply_score_delta(db_session, court, match.id, serving_team_before, 1)
    await apply_score_delta(db_session, court, match.id, serving_team_before, -1)

    records = (
        await db_session.execute(
            select(ScoreServeRecord).where(ScoreServeRecord.match_id == match.id)
        )
    ).scalars().all()
    # Only the +1 produced a record; the -1 immediately after produced none.
    assert len(records) == 1
    await db_session.refresh(match)
    assert match.serving_team == serving_team_before
    assert match.team_a_reference_server_id == team_a_ref_before
    assert match.team_b_reference_server_id == team_b_ref_before


# --- 031-shot-placement-scoring: detailed_scoring_enabled snapshot ---------


@pytest.mark.parametrize("group_setting", [True, False])
async def test_create_match_snapshots_detailed_scoring_enabled(
    db_session: AsyncSession, group_setting: bool
) -> None:
    """research.md Decision 6: Match.detailed_scoring_enabled is a snapshot
    of group.detailed_scoring_enabled taken at creation, same pattern as
    target_score/deuce_threshold/cap_score."""
    group = await _make_group(db_session, detailed_scoring_enabled=group_setting)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]

    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    assert match.detailed_scoring_enabled is group_setting


async def test_changing_group_setting_does_not_affect_existing_match(
    db_session: AsyncSession,
) -> None:
    """FR-006: a later change to the group's setting MUST NOT retroactively
    change an already-created match's snapshot."""
    group = await _make_group(db_session, detailed_scoring_enabled=False)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    group.detailed_scoring_enabled = True
    await db_session.commit()
    await db_session.refresh(match)

    assert match.detailed_scoring_enabled is False


# --- 032-score-then-record: apply_score_delta() no longer writes any -------
# --- ShotPlacementRecord itself (that's attach_shot_placement()'s job, ------
# --- tested in test_shot_placement.py) — it just returns score_event_id ----
# --- and still collapses an existing record on `-1` (FR-007). --------------


async def test_plus_one_returns_the_created_score_event_id(db_session: AsyncSession) -> None:
    """A caller (the picker's confirm(), via attach_shot_placement()) needs
    this id to pin its follow-up detail-recording call to the exact point
    that was just scored."""
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    result = await apply_score_delta(db_session, court, match.id, "A", 1)

    assert result.score_event_id is not None
    event = (
        await db_session.execute(select(ScoreEvent).where(ScoreEvent.match_id == match.id))
    ).scalar_one()
    assert result.score_event_id == str(event.id)


async def test_plus_one_never_creates_a_shot_placement_record_on_its_own(
    db_session: AsyncSession,
) -> None:
    """Regression guard: apply_score_delta() itself never writes a
    ShotPlacementRecord — score-then-record (see attach_shot_placement())
    means the score always applies on its own, detail or not."""
    group = await _make_group(db_session, detailed_scoring_enabled=True)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    await apply_score_delta(db_session, court, match.id, "A", 1)

    records = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == match.id)
        )
    ).scalars().all()
    assert records == []


async def test_minus_one_removes_last_shot_placement_record_for_that_team(
    db_session: AsyncSession,
) -> None:
    """031-shot-placement-scoring FR-007/research.md Decision 3: `delta<0`
    removes only the most recent record for the corrected team, leaving
    earlier records (and the other team's) untouched."""
    group = await _make_group(db_session, detailed_scoring_enabled=True)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    # Out-of-bounds landings (x outside [0, 1]) so the credited-side/landing
    # consistency check (attach_shot_placement()) never gets in the way —
    # this test is only about which record survives a -1, not about landing
    # rules (already covered in test_shot_placement.py).
    first = await apply_score_delta(db_session, court, match.id, "A", 1)
    await attach_shot_placement(
        db_session, court, match.id, uuid.UUID(first.score_event_id), p1.id, p2.id, -0.1, 0.5
    )
    second = await apply_score_delta(db_session, court, match.id, "A", 1)
    await attach_shot_placement(
        db_session, court, match.id, uuid.UUID(second.score_event_id), p1.id, p2.id, -0.2, 0.5
    )
    third = await apply_score_delta(db_session, court, match.id, "B", 1)
    await attach_shot_placement(
        db_session, court, match.id, uuid.UUID(third.score_event_id), p2.id, p1.id, -0.3, 0.5
    )

    await apply_score_delta(db_session, court, match.id, "A", -1)

    remaining_a = (
        await db_session.execute(
            select(ShotPlacementRecord)
            .where(ShotPlacementRecord.match_id == match.id, ShotPlacementRecord.team == "A")
            .order_by(ShotPlacementRecord.created_at)
        )
    ).scalars().all()
    assert len(remaining_a) == 1
    assert remaining_a[0].landing_x == -0.1

    remaining_b = (
        await db_session.execute(
            select(ShotPlacementRecord).where(
                ShotPlacementRecord.match_id == match.id, ShotPlacementRecord.team == "B"
            )
        )
    ).scalars().all()
    assert len(remaining_b) == 1


async def test_minus_one_on_simple_mode_match_is_a_no_op_for_shot_placement(
    db_session: AsyncSession,
) -> None:
    """A simple-mode match never has any ShotPlacementRecord to begin with —
    the delta<0 removal attempt MUST be harmless (no error, no side effect)."""
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    await apply_score_delta(db_session, court, match.id, "A", 1)
    result = await apply_score_delta(db_session, court, match.id, "A", -1)

    assert result.applied is True
    assert result.score_a == 0
