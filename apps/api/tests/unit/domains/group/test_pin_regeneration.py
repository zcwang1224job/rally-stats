"""Unit test: admin_token_version increment invalidates old tokens (FR-026/027)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import decode_admin_token, hash_admin_pin, issue_admin_token
from app.domains.group.service import regenerate_admin_pin

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="PIN Regen Test",
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


async def test_regenerate_increments_version_and_old_token_becomes_invalid(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    old_token = issue_admin_token(str(group.id), group.admin_token_version)

    new_pin, new_token = await regenerate_admin_pin(db_session, group)

    assert new_pin != "111111"
    assert group.admin_token_version == 1

    old_payload = decode_admin_token(old_token)
    new_payload = decode_admin_token(new_token)
    assert old_payload["admin_token_version"] != group.admin_token_version
    assert new_payload["admin_token_version"] == group.admin_token_version
