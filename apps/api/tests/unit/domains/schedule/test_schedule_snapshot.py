"""Unit test: build_schedule_snapshot() 之 007 擴充欄位——MatchSummary
之 score_a/score_b、CourtScheduleStatus 之 next_up（供管理頁場地控制
區塊重用，research.md #10）。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import build_schedule_snapshot, create_match_with_participants

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Schedule Snapshot Test",
        "max_members": 4,
        "match_mode": "singles",
        "scheduling_mechanism": "fair_rotation",
        "current_member_count": 1,
        "status": "active",
        "admin_pin_hash": hash_admin_pin("111111"),
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


async def _make_roster_entry(session: AsyncSession, group: Group, nickname: str) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname=nickname, status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def test_current_match_reports_scores(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1 = await _make_roster_entry(db_session, group, "小明")
    p2 = await _make_roster_entry(db_session, group, "小美")
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    match.score_a = 7
    match.score_b = 3
    await db_session.commit()

    snapshot = await build_schedule_snapshot(db_session, group)

    court_status = next(c for c in snapshot.courts if c.court_id == str(court.id))
    assert court_status.current_match is not None
    assert court_status.current_match.score_a == 7
    assert court_status.current_match.score_b == 3
    assert court_status.next_up is None


async def test_no_current_match_reports_next_up_when_queued(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1 = await _make_roster_entry(db_session, group, "小華")
    p2 = await _make_roster_entry(db_session, group, "小李")
    queued = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    snapshot = await build_schedule_snapshot(db_session, group)

    court_status = next(c for c in snapshot.courts if c.court_id == str(court.id))
    assert court_status.current_match is None
    assert court_status.waiting_reason == "no_queued_match"
    assert court_status.next_up is not None
    assert court_status.next_up.match_id == str(queued.id)


async def test_manual_mode_next_up_always_none(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="manual")
    court = await _make_court(db_session, group)

    snapshot = await build_schedule_snapshot(db_session, group)

    court_status = next(c for c in snapshot.courts if c.court_id == str(court.id))
    assert court_status.current_match is None
    assert court_status.waiting_reason == "manual_assignment"
    assert court_status.next_up is None
