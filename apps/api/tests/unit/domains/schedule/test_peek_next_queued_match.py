"""Unit test: peek_next_queued_match() 唯讀查詢（research.md #11）——
回傳下一場 queued 比賽但不修改 court_id/status，不影響後續
pull_queued_match_for_court 之領取結果。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import (
    create_match_with_participants,
    peek_next_queued_match,
    pull_queued_match_for_court,
)

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Peek Next Queued Test",
        max_members=4,
        match_mode="singles",
        scheduling_mechanism="fair_rotation",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
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


async def test_peek_returns_next_queued_match_without_mutating_it(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    queued = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    peeked = await peek_next_queued_match(db_session, group.id, 1, court.id)

    assert peeked is not None
    assert peeked.id == queued.id
    await db_session.refresh(queued)
    assert queued.status == "queued"
    assert queued.court_id is None


async def test_peek_does_not_affect_subsequent_pull(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    queued = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    peeked = await peek_next_queued_match(db_session, group.id, 1, court.id)
    assert peeked is not None

    pulled = await pull_queued_match_for_court(db_session, group.id, 1, court.id)
    await db_session.commit()

    assert pulled is not None
    assert pulled.id == queued.id
    assert pulled.status == "in_progress"
    assert pulled.court_id == court.id


async def test_peek_returns_none_when_nothing_queued(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)

    peeked = await peek_next_queued_match(db_session, group.id, 1, court.id)

    assert peeked is None
