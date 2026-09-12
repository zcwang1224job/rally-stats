"""Unit test: `_shuffle_round_match_order()` must not let a new round's
first-called match repeat the exact lineup that closed out the previous
round — a targeted exception to the otherwise-uniform `random.shuffle()` of
call-up order (service.py `_shuffle_round_match_order` docstring)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match
from app.domains.schedule.service import _shuffle_round_match_order, create_match_with_participants


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Shuffle Lineup Repeat Test",
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
async def test_shuffle_swaps_repeat_lineup_out_of_first_slot(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = await _make_group(db_session)
    entries = await _make_entries(db_session, group, 4)
    p0, p1, p2, p3 = (e.id for e in entries)

    # Round 1: p0-vs-p1 called first, p2-vs-p3 called last. Both inserts land
    # in the same transaction, so Postgres' `now()` (transaction time) would
    # otherwise tie their `created_at` — force a real ordering explicitly.
    await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p0], team_b=[p1],
    )
    match_b = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p2], team_b=[p3],
    )
    await db_session.execute(
        update(Match)
        .where(Match.id == match_b.id)
        .values(created_at=datetime.now(UTC) + timedelta(seconds=1))
    )
    await db_session.commit()

    # Round 2: one match repeats round 1's closing lineup (p2 vs p3), the
    # other doesn't (p0 vs p1).
    match_repeat = await create_match_with_participants(
        db_session, group, court_id=None, round_number=2, status="queued",
        team_a=[p2], team_b=[p3],
    )
    match_fresh = await create_match_with_participants(
        db_session, group, court_id=None, round_number=2, status="queued",
        team_a=[p0], team_b=[p1],
    )
    await db_session.commit()

    # Force the "random" shuffle to put the repeat-lineup match first —
    # deterministic regardless of the DB's unordered row return — so the
    # guard is the only thing that can move it.
    monkeypatch.setattr(
        "app.domains.schedule.service.random.shuffle",
        lambda ids: ids.sort(key=lambda mid: 0 if mid == match_repeat.id else 1),
    )

    await _shuffle_round_match_order(db_session, group.id, 2)
    await db_session.commit()

    result = await db_session.execute(
        select(Match.id)
        .where(Match.group_id == group.id, Match.round_number == 2)
        .order_by(Match.created_at)
    )
    ordered_ids = list(result.scalars())
    assert ordered_ids[0] == match_fresh.id, (
        "first match of round 2 must not repeat round 1's closing lineup"
    )
    assert ordered_ids[-1] == match_repeat.id
    assert match_b.round_number == 1  # sanity: round 1 untouched


@pytest.mark.asyncio
async def test_shuffle_is_a_noop_guard_when_no_alternative_exists(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If every match in the new round repeats the previous round's closing
    lineup (degenerate case, e.g. a single recurring pairing), the guard
    must not error or infinite-loop — it just leaves the order as shuffled."""
    group = await _make_group(db_session)
    entries = await _make_entries(db_session, group, 4)
    p0, p1, p2, p3 = (e.id for e in entries)

    await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p0], team_b=[p1],
    )
    await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p2], team_b=[p3],
    )
    await db_session.commit()

    # Both round-2 matches share the exact same lineup as round 1's closing
    # match (p2 vs p3) — no swap can help.
    await create_match_with_participants(
        db_session, group, court_id=None, round_number=2, status="queued",
        team_a=[p2], team_b=[p3],
    )
    await create_match_with_participants(
        db_session, group, court_id=None, round_number=2, status="queued",
        team_a=[p3], team_b=[p2],
    )
    await db_session.commit()

    await _shuffle_round_match_order(db_session, group.id, 2)
    await db_session.commit()

    result = await db_session.execute(
        select(Match.id).where(Match.group_id == group.id, Match.round_number == 2)
    )
    assert len(list(result.scalars())) == 2
