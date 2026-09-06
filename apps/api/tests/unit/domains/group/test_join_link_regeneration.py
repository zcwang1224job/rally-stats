"""Unit test: join-link regeneration bumps its own version but MUST NOT
publish any realtime event (spec FR-033)."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import regenerate_join_link


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Join Link Regen Test",
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


@pytest.mark.asyncio
async def test_regenerate_join_link_bumps_version_and_token(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    old_token = group.join_link_token

    updated = await regenerate_join_link(db_session, group, 0)
    assert updated.join_link_version == 1
    assert updated.join_link_token != old_token


@pytest.mark.asyncio
async def test_regenerate_join_link_does_not_publish(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = await _make_group(db_session)
    publish_mock = AsyncMock()
    monkeypatch.setattr("app.domains.group.service.publish", publish_mock)

    await regenerate_join_link(db_session, group, 0)
    publish_mock.assert_not_called()


@pytest.mark.asyncio
async def test_regenerate_join_link_stale_version_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    with pytest.raises(ApiError) as exc_info:
        await regenerate_join_link(db_session, group, 5)
    assert exc_info.value.error_code == "VERSION_CONFLICT"
