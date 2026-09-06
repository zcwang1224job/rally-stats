"""Unit test: end_match_early() 原子防呆與捨棄規則（FR-008~010、
research.md #1/#5）——轉為 abandoned、winner_team 保持 NULL（不產生
MatchResult）；已終態比賽拒絕重複提前結束（FR-006a）。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import create_match_with_participants, end_match_early

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "End Match Early Test",
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


async def _make_roster_entry(session: AsyncSession, group: Group) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname="P", status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def test_end_match_early_marks_abandoned_without_winner(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    match.score_a = 15
    match.score_b = 10
    await db_session.commit()

    result = await end_match_early(db_session, court, match.id)

    assert result.applied is True
    assert result.status == "abandoned"
    assert result.winner_team is None
    assert result.score_a == 15
    assert result.score_b == 10

    await db_session.refresh(match)
    assert match.winner_team is None


@pytest.mark.parametrize("terminal_status", ["completed", "abandoned"])
async def test_end_match_early_rejects_already_terminal_match(
    db_session: AsyncSession, terminal_status: str
) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status=terminal_status,
        team_a=[p1.id], team_b=[p2.id],
    )
    if terminal_status == "completed":
        match.winner_team = "A"
    await db_session.commit()

    result = await end_match_early(db_session, court, match.id)

    assert result.applied is False
    assert result.status == terminal_status


async def test_end_match_early_manual_mode_waits_for_admin(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="manual")
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    result = await end_match_early(db_session, court, match.id)

    assert result.applied is True
    assert result.status == "abandoned"

    await db_session.refresh(court)
    from app.domains.schedule.service import court_live_state

    state = await court_live_state(db_session, court)
    assert state.current_match is None
    assert state.waiting_reason == "manual_assignment"
