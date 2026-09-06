"""Unit test: get_my_groups() only returns groups created by the caller
(any status, disbanded included), excluding anonymously-created groups
(FR-028/029)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.schemas import CreateGroupRequest
from app.domains.group.service import create_group, disband_group
from app.domains.member.service import get_my_groups, register

pytestmark = pytest.mark.asyncio


async def test_my_groups_excludes_anonymous_and_other_members_groups(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "mygroups1@example.com", "abc12345")
    member.nickname = "王甲"
    other_member = await register(db_session, "mygroups2@example.com", "abc12345")
    other_member.nickname = "王乙"
    await db_session.commit()

    payload = CreateGroupRequest(
        name="My Group",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    await create_group(db_session, payload, member=member)
    await create_group(
        db_session,
        CreateGroupRequest(
            name="Anonymous Group",
            max_members=4,
            match_mode="doubles",
            scheduling_mechanism="manual",
            creator_nickname="訪客",
            turnstile_token="unused",
        ),
        member=None,
    )
    await create_group(db_session, payload, member=other_member)

    result = await get_my_groups(db_session, member.id)

    assert len(result.groups) == 1
    assert result.groups[0].name == "My Group"


async def test_my_groups_includes_disbanded_groups(db_session: AsyncSession) -> None:
    member = await register(db_session, "mygroups3@example.com", "abc12345")
    member.nickname = "王丙"
    await db_session.commit()
    payload = CreateGroupRequest(
        name="Will Disband",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, _roster_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=member
    )
    await disband_group(db_session, group)

    result = await get_my_groups(db_session, member.id)

    assert len(result.groups) == 1
    assert result.groups[0].status == "disbanded"
