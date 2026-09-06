"""Unit test: resolve_join_link() — queries by join_link_token, raises
LINK_NOT_FOUND when unknown (US2)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import resolve_join_link

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Join Link Test",
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


async def test_resolve_join_link_finds_group(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    resolved = await resolve_join_link(db_session, group.join_link_token)
    assert resolved.id == group.id


async def test_resolve_join_link_unknown_token_raises(db_session: AsyncSession) -> None:
    with pytest.raises(ApiError) as exc_info:
        await resolve_join_link(db_session, uuid.uuid4())
    assert exc_info.value.error_code == "LINK_NOT_FOUND"
