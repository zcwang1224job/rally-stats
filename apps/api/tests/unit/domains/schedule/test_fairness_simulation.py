"""SC-002 multi-round fairness simulation: when the active roster size is
evenly divisible by per-round capacity (`courts * per_match`), the gap
between any two active participants' cumulative appearance counts must never
exceed 1, no matter how many rounds run. Each `generate_next_round()` call
force-abandons the prior round (FR-032) and immediately generates a new one,
which is sufficient to drive `wait_count`/selection without needing to
actually complete any match."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import MatchParticipant
from app.domains.schedule.service import generate_next_round

PLAYER_COUNT = 12
ROUNDS = 9  # 9 rounds * 4 players/round = 36 slots / 12 players = 3 turns each on average


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Fairness Simulation",
        max_members=PLAYER_COUNT,
        match_mode="doubles",
        scheduling_mechanism="fair_rotation",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


@pytest.mark.asyncio
async def test_appearance_counts_stay_within_one_of_each_other(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = Court(group_id=group.id, name="1號場")
    db_session.add(court)
    await db_session.commit()

    roster_ids = []
    for i in range(PLAYER_COUNT):
        entry = RosterEntry(group_id=group.id, nickname=f"P{i}", status="active")
        db_session.add(entry)
        roster_ids.append(entry)
    await db_session.commit()
    for entry in roster_ids:
        await db_session.refresh(entry)
    all_ids = {entry.id for entry in roster_ids}

    for _ in range(ROUNDS):
        group = await generate_next_round(db_session, group)

    result = await db_session.execute(
        select(MatchParticipant.roster_entry_id, func.count())
        .where(MatchParticipant.roster_entry_id.in_(all_ids))
        .group_by(MatchParticipant.roster_entry_id)
    )
    counts_by_id: dict[uuid.UUID, int] = dict(result.all())

    # Everyone MUST have appeared at least once — a 0-appearance player would
    # trivially violate the ≤1 gap and indicates a selection bug, not fairness.
    counts = [counts_by_id.get(entry.id, 0) for entry in roster_ids]
    assert min(counts) > 0
    assert max(counts) - min(counts) <= 1
