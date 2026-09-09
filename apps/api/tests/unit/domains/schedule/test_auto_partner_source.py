"""Unit test: partner_source == "auto" computes teams fresh each round from
PairHistory (least-paired-first), via a function distinct from the existing
auto_pair_on_enter_fixed_partner() one-time join-order fallback
(011-round-robin-scheduling FR-009, research.md #6 naming clarification)."""

import math

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, Partnership
from app.domains.schedule.service import compute_auto_partner_teams_for_round, generate_next_round


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Auto Partner Source Test",
        "max_members": 16,
        "match_mode": "doubles",
        "scheduling_mechanism": "fixed_partner",
        "partner_source": "auto",
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
async def test_auto_source_pairs_the_whole_active_roster(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entries = await _make_entries(db_session, group, 8)

    teams = await compute_auto_partner_teams_for_round(db_session, group.id)

    assert len(teams) == 4
    paired_ids = {pid for team in teams for pid in team}
    assert paired_ids == {e.id for e in entries}


@pytest.mark.asyncio
async def test_auto_source_never_writes_to_partnerships(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 8)

    await generate_next_round(db_session, group)

    result = await db_session.execute(select(Match).where(Match.group_id == group.id))
    assert len(result.scalars().all()) == math.comb(4, 2)

    partnerships = await db_session.execute(
        select(Partnership).where(Partnership.group_id == group.id)
    )
    assert partnerships.scalars().all() == []


@pytest.mark.asyncio
async def test_temporary_pairings_are_ignored_when_partner_source_is_auto(
    db_session: AsyncSession,
) -> None:
    """017-fixed-partner-autofill FR-005/US3: `temporary_pairings` is a
    "manual" partner_source concept only — passing it while partner_source
    == "auto" MUST NOT change the (still history-optimized) result."""
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    entries = await _make_entries(db_session, group, 8)

    bogus_pairings = [(entries[0].id, entries[1].id), (entries[2].id, entries[3].id)]
    await generate_next_round(db_session, group, bogus_pairings)

    result = await db_session.execute(select(Match).where(Match.group_id == group.id))
    assert len(result.scalars().all()) == math.comb(4, 2)

    partnerships = await db_session.execute(
        select(Partnership).where(Partnership.group_id == group.id)
    )
    assert partnerships.scalars().all() == []
