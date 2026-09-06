"""Unit test: _generate_fair_rotation_matches() singles branch produces a
full round-robin schedule (every active member plays every other member
exactly once) per 011-round-robin-scheduling FR-002 / research.md #1 — not
the old "fill exactly len(courts) matches" behavior."""

import math

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant
from app.domains.schedule.service import generate_next_round


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Singles Round Robin Test",
        "max_members": 16,
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


async def _make_entries(session: AsyncSession, group: Group, count: int) -> list[RosterEntry]:
    entries = [
        RosterEntry(group_id=group.id, nickname=f"P{i}", status="active") for i in range(count)
    ]
    session.add_all(entries)
    await session.commit()
    for entry in entries:
        await session.refresh(entry)
    return entries


@pytest.mark.asyncio
async def test_singles_round_robin_covers_every_pair_once(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    entries = await _make_entries(db_session, group, 5)
    entry_ids = {e.id for e in entries}

    await generate_next_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    matches = result.scalars().all()
    assert len(matches) == math.comb(5, 2)

    seen_pairs: set[frozenset] = set()
    for match in matches:
        assert match.status in ("queued", "in_progress")
        participants_result = await db_session.execute(
            select(MatchParticipant.roster_entry_id).where(MatchParticipant.match_id == match.id)
        )
        pair = frozenset(participants_result.scalars())
        assert len(pair) == 2
        assert pair <= entry_ids
        assert pair not in seen_pairs
        seen_pairs.add(pair)

    assert len(seen_pairs) == math.comb(5, 2)


@pytest.mark.asyncio
async def test_singles_round_robin_leaves_at_most_one_court_worth_in_progress(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    updated = await generate_next_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(
            Match.group_id == group.id, Match.round_number == 1, Match.status == "in_progress"
        )
    )
    in_progress = result.scalars().all()
    assert len(in_progress) == 1  # only one court -> only one match picked up
    assert updated.current_round_number == 1
