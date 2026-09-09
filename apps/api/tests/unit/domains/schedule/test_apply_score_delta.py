"""Unit test: apply_score_delta() 原子防呆（FR-005/006/006a/007）與達標
後之終態轉換 + advance_court_after_match_ends hook 呼叫（research.md #5/#6）."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import ScoreEvent
from app.domains.schedule.service import apply_score_delta, create_match_with_participants

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
                select(ScoreEvent).where(ScoreEvent.match_id == match.id).order_by(ScoreEvent.created_at)
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
