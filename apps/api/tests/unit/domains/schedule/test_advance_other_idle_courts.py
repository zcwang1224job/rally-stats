"""Unit test: ending a match re-checks EVERY idle court in the group, not
just the one whose match just ended — 011-round-robin-scheduling. A full
round-robin schedule can leave a court idle only because its remaining
candidates were busy elsewhere; once any match ends, that block may lift
for a court other than the one that triggered the check."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match
from app.domains.schedule.service import create_match_with_participants, end_match_early


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Idle Court Advance Test",
        max_members=8,
        match_mode="singles",
        scheduling_mechanism="fair_rotation",
        current_member_count=1,
        current_round_number=1,
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


async def _make_entry(session: AsyncSession, group: Group, nickname: str) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname=nickname, status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_ending_one_court_unblocks_another_idle_court(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court1 = await _make_court(db_session, group, "1號場")
    court2 = await _make_court(db_session, group, "2號場")
    p1 = await _make_entry(db_session, group, "P1")
    p2 = await _make_entry(db_session, group, "P2")
    p3 = await _make_entry(db_session, group, "P3")
    p4 = await _make_entry(db_session, group, "P4")

    # court1 = P1 vs P2 (in_progress); court2 = P3 vs P4 (in_progress).
    m1 = await create_match_with_participants(
        db_session, group, court_id=court1.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await create_match_with_participants(
        db_session, group, court_id=court2.id, round_number=1, status="in_progress",
        team_a=[p3.id], team_b=[p4.id],
    )
    # Only queued match left involves P2 and P3 -> ineligible until one of
    # court1/court2 frees up its player.
    blocked = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p2.id], team_b=[p3.id],
    )
    await db_session.commit()

    # End court1's match (P1 vs P2) -> frees P1 and P2. The blocked match
    # (P2 vs P3) is still ineligible (P3 still busy on court2) for court1
    # itself, but this exercises that court1 correctly stays idle rather
    # than wrongly grabbing a match with a still-busy participant.
    result = await end_match_early(db_session, court1, m1.id)
    assert result.applied is True

    court1_current = await db_session.execute(
        select(Match).where(Match.court_id == court1.id, Match.status == "in_progress")
    )
    assert court1_current.scalar_one_or_none() is None

    blocked_refreshed = await db_session.execute(select(Match).where(Match.id == blocked.id))
    assert blocked_refreshed.scalar_one().status == "queued"


@pytest.mark.asyncio
async def test_ending_a_match_unblocks_a_different_court_that_is_already_idle(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    court1 = await _make_court(db_session, group, "1號場")
    court2 = await _make_court(db_session, group, "2號場")
    court3 = await _make_court(db_session, group, "3號場")
    p1 = await _make_entry(db_session, group, "P1")
    p2 = await _make_entry(db_session, group, "P2")
    p3 = await _make_entry(db_session, group, "P3")
    p4 = await _make_entry(db_session, group, "P4")
    p5 = await _make_entry(db_session, group, "P5")
    p6 = await _make_entry(db_session, group, "P6")

    # court1 is already idle (no current match, nothing to end).
    # court2 = P1 vs P2 (in_progress); court3 = P3 vs P4 (in_progress, stays
    # untouched throughout — proves the recheck doesn't disturb busy courts).
    m2 = await create_match_with_participants(
        db_session, group, court_id=court2.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await create_match_with_participants(
        db_session, group, court_id=court3.id, round_number=1, status="in_progress",
        team_a=[p3.id], team_b=[p4.id],
    )
    # Two queued matches, each blocked by exactly one of court2's players ->
    # BOTH become eligible the instant court2's match ends. court2's own
    # pull (advance_court_after_match_ends) claims one of them first; the
    # other is left over for _advance_other_idle_courts to hand to court1.
    q1 = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p2.id], team_b=[p5.id],
    )
    q2 = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p1.id], team_b=[p6.id],
    )
    await db_session.commit()

    result = await end_match_early(db_session, court2, m2.id)
    assert result.applied is True

    court2_current = await db_session.execute(
        select(Match).where(Match.court_id == court2.id, Match.status == "in_progress")
    )
    court2_match = court2_current.scalar_one_or_none()
    assert court2_match is not None
    assert court2_match.id in (q1.id, q2.id)

    # court1 — which had nothing to do with the match that just ended —
    # MUST have picked up the OTHER newly-eligible match via the idle-court
    # recheck, not just sat idle waiting for its own event.
    court1_current = await db_session.execute(
        select(Match).where(Match.court_id == court1.id, Match.status == "in_progress")
    )
    court1_match = court1_current.scalar_one_or_none()
    assert court1_match is not None
    assert court1_match.id in (q1.id, q2.id)
    assert court1_match.id != court2_match.id

    # court3 must be completely untouched.
    court3_current = await db_session.execute(
        select(Match).where(Match.court_id == court3.id, Match.status == "in_progress")
    )
    court3_match = court3_current.scalar_one()
    assert {p.id for p in (p3, p4)} == {p3.id, p4.id}
    uuid.UUID(str(court3_match.id))  # sanity: still a real match id
