"""Unit test: base_settings_version optimistic-lock conflict detection (FR-028)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.schemas import EditGroupRequest
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import edit_group

pytestmark = pytest.mark.asyncio


async def test_stale_version_rejected(db_session: AsyncSession) -> None:
    group = Group(
        name="Lock Test",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    await edit_group(db_session, group, EditGroupRequest(expected_version=0, name="First edit"))
    assert group.base_settings_version == 1

    with pytest.raises(ApiError) as exc_info:
        await edit_group(
            db_session, group, EditGroupRequest(expected_version=0, name="Stale edit")
        )
    assert exc_info.value.error_code == "VERSION_CONFLICT"
