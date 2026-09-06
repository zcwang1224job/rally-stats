"""Unit test: FR-013 manual-assign guard checks — already playing elsewhere,
already left/kicked, duplicate participant in the same match."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import create_match_with_participants, manual_assign


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Manual Assign Test",
        "max_members": 4,
        "match_mode": "doubles",
        "scheduling_mechanism": "manual",
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


async def _make_roster_entry(
    session: AsyncSession, group: Group, status: str = "active"
) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname="P", status=status)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_rejects_participant_already_playing_elsewhere(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court_a = await _make_court(db_session, group)
    court_b = Court(group_id=group.id, name="2號場")
    db_session.add(court_b)
    await db_session.commit()
    await db_session.refresh(court_b)

    p1, p2, p3, p4, p5 = [await _make_roster_entry(db_session, group) for _ in range(5)]
    await create_match_with_participants(
        db_session, group, court_id=court_a.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await manual_assign(
            db_session, group, court_b,
            team_a=[p1.id, p3.id], team_b=[p4.id, p5.id],
        )
    assert exc_info.value.error_code == "PARTICIPANT_ALREADY_PLAYING"


@pytest.mark.asyncio
async def test_rejects_left_member(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2, p3 = [await _make_roster_entry(db_session, group) for _ in range(3)]
    left = await _make_roster_entry(db_session, group, status="left")

    with pytest.raises(ApiError) as exc_info:
        await manual_assign(
            db_session, group, court, team_a=[p1.id, p2.id], team_b=[p3.id, left.id]
        )
    assert exc_info.value.error_code == "PARTICIPANT_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_rejects_duplicate_participant(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2, p3 = [await _make_roster_entry(db_session, group) for _ in range(3)]

    with pytest.raises(ApiError) as exc_info:
        await manual_assign(
            db_session, group, court, team_a=[p1.id, p2.id], team_b=[p2.id, p3.id]
        )
    assert exc_info.value.error_code == "DUPLICATE_PARTICIPANT"


@pytest.mark.asyncio
async def test_rejects_when_court_already_has_in_progress_match(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2, p3, p4 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await manual_assign(db_session, group, court, team_a=[p3.id], team_b=[p4.id])
    assert exc_info.value.error_code == "COURT_NOT_WAITING"


@pytest.mark.asyncio
async def test_rejects_non_manual_scheduling_mechanism(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="fair_rotation")
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]

    with pytest.raises(ApiError) as exc_info:
        await manual_assign(db_session, group, court, team_a=[p1.id], team_b=[p2.id])
    assert exc_info.value.error_code == "SCHEDULING_MECHANISM_MISMATCH"


@pytest.mark.asyncio
async def test_rejects_roster_entry_from_a_different_group(db_session: AsyncSession) -> None:
    """Security review (T078): a roster_entry_id belonging to another group
    MUST NOT be assignable into this group's match, even if it happens to be
    active there — otherwise an admin could cross-reference another group's
    roster into their own match_participants rows."""
    group = await _make_group(db_session)
    other_group = await _make_group(db_session, name="Other Group")
    court = await _make_court(db_session, group)
    p1, p2, p3 = [await _make_roster_entry(db_session, group) for _ in range(3)]
    foreign = await _make_roster_entry(db_session, other_group)

    with pytest.raises(ApiError) as exc_info:
        await manual_assign(
            db_session, group, court, team_a=[p1.id, p2.id], team_b=[p3.id, foreign.id]
        )
    assert exc_info.value.error_code == "PARTICIPANT_NOT_ACTIVE"
