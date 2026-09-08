"""Unit test: disband_group service logic (idempotency, status transition,
abandon-matches hook invocation per spec FR-029-033)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import disband_group

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Disband Test",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def test_disband_transitions_status(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    assert group.disbanded_at is None
    updated = await disband_group(db_session, group)
    assert updated.status == "disbanded"
    assert updated.disbanded_at is not None


async def test_disband_is_idempotent(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await disband_group(db_session, group)
    first_disbanded_at = group.disbanded_at
    # Re-disbanding an already-disbanded group must be a no-op, not an error
    # (manual disband racing the auto-disband sweep) — including not
    # bumping disbanded_at a second time.
    result = await disband_group(db_session, group)
    assert result.status == "disbanded"
    assert result.disbanded_at == first_disbanded_at


async def test_disband_invokes_abandon_matches_hook(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    calls: list[str] = []

    async def hook(_session: AsyncSession, group_id: object) -> None:
        calls.append(str(group_id))

    await disband_group(db_session, group, abandon_unfinished_matches=hook)
    assert calls == [str(group.id)]
