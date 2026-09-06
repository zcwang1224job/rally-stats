"""Unit test: `generate_next_round()` writes a `round_history` row in the
same transaction as `current_round_number`'s update, one row per round
generated — including round 1, whose first generation leaves
`current_round_number` at its group-creation default (1) instead of
pre-incrementing to 2 and skipping round 1 entirely (research.md #1, #2 of
005-member-view)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group, RoundHistory
from app.domains.group.security import hash_admin_pin
from app.domains.schedule.service import generate_next_round


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Round History Test",
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


@pytest.mark.asyncio
async def test_generate_next_round_writes_round_history(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)

    await generate_next_round(db_session, group)

    result = await db_session.execute(
        select(RoundHistory).where(
            RoundHistory.group_id == group.id, RoundHistory.round_number == 1
        )
    )
    row = result.scalar_one()
    assert row.started_at is not None


@pytest.mark.asyncio
async def test_generate_next_round_does_not_increment_on_first_call(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)

    updated = await generate_next_round(db_session, group)

    assert updated.current_round_number == 1


@pytest.mark.asyncio
async def test_generate_next_round_writes_one_row_per_call(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="manual")
    await _make_court(db_session, group)

    await generate_next_round(db_session, group)
    await generate_next_round(db_session, group)

    result = await db_session.execute(
        select(RoundHistory).where(RoundHistory.group_id == group.id)
    )
    rows = result.scalars().all()
    assert sorted(r.round_number for r in rows) == [1, 2]
