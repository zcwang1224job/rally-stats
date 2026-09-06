"""Unit test: remove_roster_entry_from_schedule / handle_member_left /
kick_member — FR-039/040/041. Queued matches containing the removed member
are abandoned entirely (matches are always exactly-sized, so partial removal
never leaves a valid match); in-progress matches are untouched; nothing here
triggers a round regeneration."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant
from app.domains.schedule.service import (
    handle_member_left,
    kick_member,
    remove_roster_entry_from_schedule,
)


async def _make_group(session: AsyncSession, mechanism: str = "fair_rotation") -> Group:
    group = Group(
        name="Member Removal Test",
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism=mechanism,
        current_round_number=1,
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_roster_entry(session: AsyncSession, group: Group, nickname: str) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname=nickname, status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def _make_match_with_participants(
    session: AsyncSession,
    group: Group,
    status: str,
    round_number: int,
    participant_ids: list[uuid.UUID],
    court: Court | None = None,
) -> Match:
    match = Match(
        group_id=group.id,
        court_id=court.id if court else None,
        round_number=round_number,
        status=status,
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
    )
    session.add(match)
    await session.flush()
    session.add_all(
        [
            MatchParticipant(match_id=match.id, roster_entry_id=pid, team="A" if i < 1 else "B")
            for i, pid in enumerate(participant_ids)
        ]
    )
    await session.commit()
    await session.refresh(match)
    return match


@pytest.mark.asyncio
async def test_removal_abandons_queued_match_containing_member(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_roster_entry(db_session, group, "A")
    b = await _make_roster_entry(db_session, group, "B")
    match = await _make_match_with_participants(db_session, group, "queued", 1, [a.id, b.id])

    await remove_roster_entry_from_schedule(db_session, group, a.id)
    await db_session.commit()

    await db_session.refresh(match)
    assert match.status == "abandoned"


@pytest.mark.asyncio
async def test_removal_does_not_touch_in_progress_match(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = Court(group_id=group.id, name="1號場")
    db_session.add(court)
    await db_session.commit()
    await db_session.refresh(court)

    a = await _make_roster_entry(db_session, group, "A")
    b = await _make_roster_entry(db_session, group, "B")
    match = await _make_match_with_participants(
        db_session, group, "in_progress", 1, [a.id, b.id], court=court
    )

    await remove_roster_entry_from_schedule(db_session, group, a.id)
    await db_session.commit()

    await db_session.refresh(match)
    assert match.status == "in_progress"


@pytest.mark.asyncio
async def test_removal_does_not_touch_other_queued_matches(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_roster_entry(db_session, group, "A")
    b = await _make_roster_entry(db_session, group, "B")
    c = await _make_roster_entry(db_session, group, "C")
    d = await _make_roster_entry(db_session, group, "D")
    unrelated = await _make_match_with_participants(db_session, group, "queued", 1, [c.id, d.id])
    removed_from = await _make_match_with_participants(db_session, group, "queued", 1, [a.id, b.id])

    await remove_roster_entry_from_schedule(db_session, group, a.id)
    await db_session.commit()

    await db_session.refresh(unrelated)
    await db_session.refresh(removed_from)
    assert unrelated.status == "queued"
    assert removed_from.status == "abandoned"


@pytest.mark.asyncio
async def test_removal_ignores_previous_rounds(db_session: AsyncSession) -> None:
    """Only the group's *current* round's queued matches are converged —
    stale queued rows from a prior round should not exist in practice, but
    the query is scoped defensively anyway."""
    group = await _make_group(db_session)
    group.current_round_number = 2
    await db_session.commit()
    await db_session.refresh(group)

    a = await _make_roster_entry(db_session, group, "A")
    b = await _make_roster_entry(db_session, group, "B")
    old_round_match = await _make_match_with_participants(
        db_session, group, "queued", 1, [a.id, b.id]
    )

    await remove_roster_entry_from_schedule(db_session, group, a.id)
    await db_session.commit()
    await db_session.refresh(old_round_match)
    assert old_round_match.status == "queued"


@pytest.mark.asyncio
async def test_handle_member_left_converges_schedule_and_sets_status(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a = await _make_roster_entry(db_session, group, "A")
    b = await _make_roster_entry(db_session, group, "B")
    match = await _make_match_with_participants(db_session, group, "queued", 1, [a.id, b.id])

    await handle_member_left(db_session, group, a, new_status="left")
    await db_session.commit()

    await db_session.refresh(a)
    await db_session.refresh(match)
    assert a.status == "left"
    assert match.status == "abandoned"


@pytest.mark.asyncio
async def test_handle_member_left_decrements_current_member_count(
    db_session: AsyncSession,
) -> None:
    """Regression test: current_member_count previously only ever had its
    increment implemented (join_group's atomic +1) — nothing decremented it
    on a leave/kick, so a group with turnover would eventually hit
    max_members and start rejecting new joins even with barely anyone
    actually active."""
    group = await _make_group(db_session)
    group.current_member_count = 2
    await db_session.commit()
    a = await _make_roster_entry(db_session, group, "A")

    await handle_member_left(db_session, group, a, new_status="left")
    await db_session.commit()

    await db_session.refresh(group)
    assert group.current_member_count == 1


@pytest.mark.asyncio
async def test_kick_member_sets_kicked_status(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_roster_entry(db_session, group, "A")

    updated = await kick_member(db_session, group, a)

    assert updated.status == "kicked"


@pytest.mark.asyncio
async def test_kick_member_decrements_current_member_count(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    group.current_member_count = 2
    await db_session.commit()
    a = await _make_roster_entry(db_session, group, "A")

    await kick_member(db_session, group, a)

    await db_session.refresh(group)
    assert group.current_member_count == 1


@pytest.mark.asyncio
async def test_kick_member_rejects_already_left_entry(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_roster_entry(db_session, group, "A")
    a.status = "left"
    await db_session.commit()

    from app.core.errors import ApiError

    with pytest.raises(ApiError) as exc_info:
        await kick_member(db_session, group, a)
    assert exc_info.value.error_code == "ROSTER_ENTRY_ALREADY_LEFT"


@pytest.mark.asyncio
async def test_kick_member_rejects_entry_from_a_different_group(db_session: AsyncSession) -> None:
    """Security review (T078): kicking a roster_entry_id that belongs to a
    different group MUST NOT succeed, even with a valid admin token for the
    caller's own group — otherwise an admin could mutate another group's
    roster by ID guessing."""
    group = await _make_group(db_session)
    other_group = await _make_group(db_session)
    foreign = await _make_roster_entry(db_session, other_group, "Foreign")

    from app.core.errors import ApiError

    with pytest.raises(ApiError) as exc_info:
        await kick_member(db_session, group, foreign)
    assert exc_info.value.error_code == "ROSTER_ENTRY_NOT_FOUND"
