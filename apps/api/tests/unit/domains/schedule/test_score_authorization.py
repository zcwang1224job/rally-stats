"""Unit test: apply_score_delta()/end_match_early() reject a match_id that
doesn't belong to the resolved court — a delayed request retargeted at the
wrong court's match MUST NOT silently succeed (research.md #4)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import (
    apply_score_delta,
    create_match_with_participants,
    end_match_early,
)

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Score Authorization Test",
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


async def _make_court(session: AsyncSession, group: Group, name: str) -> Court:
    court = Court(group_id=group.id, name=name)
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


async def test_apply_score_delta_rejects_match_from_other_court(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court_a = await _make_court(db_session, group, "1號場")
    court_b = await _make_court(db_session, group, "2號場")
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match_on_b = await create_match_with_participants(
        db_session, group, court_id=court_b.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await apply_score_delta(db_session, court_a, match_on_b.id, "A", 1)
    assert exc_info.value.error_code == "MATCH_NOT_FOUND"


async def test_end_match_early_rejects_match_from_other_court(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court_a = await _make_court(db_session, group, "1號場")
    court_b = await _make_court(db_session, group, "2號場")
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match_on_b = await create_match_with_participants(
        db_session, group, court_id=court_b.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await end_match_early(db_session, court_a, match_on_b.id)
    assert exc_info.value.error_code == "MATCH_NOT_FOUND"


async def test_apply_score_delta_rejects_nonexistent_match(db_session: AsyncSession) -> None:
    import uuid

    group = await _make_group(db_session)
    court = await _make_court(db_session, group, "1號場")

    with pytest.raises(ApiError) as exc_info:
        await apply_score_delta(db_session, court, uuid.uuid4(), "A", 1)
    assert exc_info.value.error_code == "MATCH_NOT_FOUND"
