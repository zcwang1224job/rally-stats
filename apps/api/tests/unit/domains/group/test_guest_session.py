"""Unit test: resolve_guest_session() — valid token returns the roster
entry; unknown token, non-active roster entry, or disbanded group all raise
LINK_NOT_FOUND without distinguishing which (research.md #4, US4)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import join_group, resolve_guest_session

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Guest Session Test",
        max_members=8,
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


async def test_resolve_guest_session_returns_roster_entry(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )

    resolved = await resolve_guest_session(db_session, roster_entry.guest_session_token)
    assert resolved.id == roster_entry.id


async def test_resolve_guest_session_unknown_token_raises(db_session: AsyncSession) -> None:
    with pytest.raises(ApiError) as exc_info:
        await resolve_guest_session(db_session, "not-a-real-token")
    assert exc_info.value.error_code == "LINK_NOT_FOUND"


async def test_resolve_guest_session_after_group_disbanded_raises(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    group.status = "disbanded"
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await resolve_guest_session(db_session, roster_entry.guest_session_token)
    assert exc_info.value.error_code == "LINK_NOT_FOUND"


async def test_resolve_guest_session_after_left_raises(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    roster_entry.status = "left"
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await resolve_guest_session(db_session, roster_entry.guest_session_token)
    assert exc_info.value.error_code == "LINK_NOT_FOUND"
