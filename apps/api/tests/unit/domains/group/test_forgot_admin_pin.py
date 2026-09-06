"""Unit test: forgot_admin_pin() only works for the group's own creator,
including on an already-disbanded group (FR-028~032)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.schemas import CreateGroupRequest
from app.domains.group.service import create_group, disband_group, forgot_admin_pin
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def test_forgot_admin_pin_rejects_non_creator(db_session: AsyncSession) -> None:
    creator = await register(db_session, "forgotpin1@example.com", "abc12345")
    creator.nickname = "王甲"
    other_member = await register(db_session, "forgotpin2@example.com", "abc12345")
    other_member.nickname = "王乙"
    await db_session.commit()

    group, _roster_entry, _pin, _guest_token = await create_group(
        db_session,
        CreateGroupRequest(
            name="Forgot Pin Group",
            max_members=4,
            match_mode="doubles",
            scheduling_mechanism="manual",
            turnstile_token="unused",
        ),
        member=creator,
    )

    with pytest.raises(ApiError) as exc_info:
        await forgot_admin_pin(db_session, group.id, other_member.id)
    assert exc_info.value.error_code == "NOT_GROUP_CREATOR"


async def test_forgot_admin_pin_rejects_anonymously_created_group(db_session: AsyncSession) -> None:
    member = await register(db_session, "forgotpin3@example.com", "abc12345")
    member.nickname = "王丙"
    await db_session.commit()

    group, _roster_entry, _pin, _guest_token = await create_group(
        db_session,
        CreateGroupRequest(
            name="Anonymous Forgot Pin",
            max_members=4,
            match_mode="doubles",
            scheduling_mechanism="manual",
            creator_nickname="訪客",
            turnstile_token="unused",
        ),
        member=None,
    )

    with pytest.raises(ApiError) as exc_info:
        await forgot_admin_pin(db_session, group.id, member.id)
    assert exc_info.value.error_code == "NOT_GROUP_CREATOR"


async def test_forgot_admin_pin_succeeds_on_disbanded_group(db_session: AsyncSession) -> None:
    member = await register(db_session, "forgotpin4@example.com", "abc12345")
    member.nickname = "王丁"
    await db_session.commit()

    group, _roster_entry, old_pin, _guest_token = await create_group(
        db_session,
        CreateGroupRequest(
            name="Disbanded Forgot Pin",
            max_members=4,
            match_mode="doubles",
            scheduling_mechanism="manual",
            turnstile_token="unused",
        ),
        member=member,
    )
    await disband_group(db_session, group)

    new_pin, new_token = await forgot_admin_pin(db_session, group.id, member.id)

    assert new_pin != old_pin
    assert new_token != ""
