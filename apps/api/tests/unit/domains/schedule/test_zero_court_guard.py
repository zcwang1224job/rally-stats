"""Unit test: zero-court guard — Next Round rejected outright, and Auto Next
Round silently declines to attempt generation (spec FR-029/030)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.schedule.service import (
    check_round_complete_and_maybe_auto_advance,
    generate_next_round,
)


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Zero Court Guard Test",
        "max_members": 4,
        "match_mode": "singles",
        "scheduling_mechanism": "fair_rotation",
        "current_member_count": 1,
        "status": "active",
        "admin_pin_hash": hash_admin_pin("111111"),
        "auto_next_round": True,
    }
    defaults.update(overrides)
    group = Group(**defaults)  # type: ignore[arg-type]
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


@pytest.mark.asyncio
async def test_next_round_rejected_with_no_courts(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    with pytest.raises(ApiError) as exc_info:
        await generate_next_round(db_session, group)
    assert exc_info.value.error_code == "NO_COURTS_AVAILABLE"
    assert group.current_round_number == 1  # unchanged


@pytest.mark.asyncio
async def test_auto_next_round_does_not_attempt_with_no_courts(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    # No matches at all for round 1 -> round_is_complete() is vacuously True,
    # but with zero courts, auto-advance MUST NOT even try to generate.
    advanced = await check_round_complete_and_maybe_auto_advance(db_session, group)
    assert advanced is False
    assert group.current_round_number == 1
