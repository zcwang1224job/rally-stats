"""Unit test: advance_court_after_match_ends pulls the next queued match for
the same court, or leaves it idle when nothing is queued; manual mode is a
no-op (spec FR-027, research.md #10)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import (
    advance_court_after_match_ends,
    create_match_with_participants,
)


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Advance Court Test",
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


@pytest.mark.asyncio
async def test_pulls_next_queued_match_for_same_court(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2, p3, p4 = [await _make_roster_entry(db_session, group) for _ in range(4)]

    finished = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    queued = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p3.id], team_b=[p4.id],
    )
    finished.status = "completed"
    await db_session.commit()

    pulled = await advance_court_after_match_ends(db_session, finished)
    await db_session.commit()

    assert pulled is not None
    assert pulled.id == queued.id
    assert pulled.court_id == court.id
    assert pulled.status == "in_progress"


@pytest.mark.asyncio
async def test_returns_none_when_nothing_queued(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1 = await _make_roster_entry(db_session, group)

    p2 = await _make_roster_entry(db_session, group)
    finished = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    finished.status = "completed"
    await db_session.commit()

    pulled = await advance_court_after_match_ends(db_session, finished)
    assert pulled is None


@pytest.mark.asyncio
async def test_manual_mode_is_noop(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="manual")
    court = await _make_court(db_session, group)
    p1 = await _make_roster_entry(db_session, group)

    p2 = await _make_roster_entry(db_session, group)
    finished = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    finished.status = "completed"
    await db_session.commit()

    pulled = await advance_court_after_match_ends(db_session, finished)
    assert pulled is None
