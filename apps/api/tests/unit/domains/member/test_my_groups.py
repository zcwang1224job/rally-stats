"""Unit test: get_my_groups() — originally only returned groups created by
the caller (FR-028/029); 014-member-groups-history extends it to the union
of self-created ∪ ever-a-roster-member groups (any status), each annotated
with is_creator/member_status (FR-001~003)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.schemas import CreateGroupRequest
from app.domains.group.service import create_group, disband_group, join_group, leave_group
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


async def test_my_groups_includes_creator_own_entry_flags(db_session: AsyncSession) -> None:
    member = await register(db_session, "mygroups4@example.com", "abc12345")
    member.nickname = "王丁"
    await db_session.commit()
    payload = CreateGroupRequest(
        name="Created By Me",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    await create_group(db_session, payload, member=member)

    result = await get_my_groups(db_session, member.id)

    assert len(result.groups) == 1
    assert result.groups[0].is_creator is True
    assert result.groups[0].member_status == "active"


async def test_my_groups_includes_group_joined_but_not_created(db_session: AsyncSession) -> None:
    creator = await register(db_session, "mygroups5@example.com", "abc12345")
    creator.nickname = "團長"
    joiner = await register(db_session, "mygroups6@example.com", "abc12345")
    joiner.nickname = "團員"
    await db_session.commit()
    payload = CreateGroupRequest(
        name="Joined Group",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, _roster_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=creator
    )
    await join_group(db_session, group, member=joiner, password=None, nickname=None)

    result = await get_my_groups(db_session, joiner.id)

    assert len(result.groups) == 1
    assert result.groups[0].is_creator is False
    assert result.groups[0].member_status == "active"


async def test_my_groups_shows_left_status_after_leaving(db_session: AsyncSession) -> None:
    creator = await register(db_session, "mygroups7@example.com", "abc12345")
    creator.nickname = "團長2"
    joiner = await register(db_session, "mygroups8@example.com", "abc12345")
    joiner.nickname = "團員2"
    await db_session.commit()
    payload = CreateGroupRequest(
        name="Left Group",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, _roster_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=creator
    )
    roster_entry, _created_new = await join_group(
        db_session, group, member=joiner, password=None, nickname=None
    )
    await leave_group(
        db_session, group, roster_entry.id, guest_session_token=None, member_id=joiner.id
    )

    result = await get_my_groups(db_session, joiner.id)

    assert len(result.groups) == 1
    assert result.groups[0].member_status == "left"


async def test_my_groups_does_not_duplicate_group_creator_created_and_joined(
    db_session: AsyncSession,
) -> None:
    """A creator's own RosterEntry means they'd otherwise match BOTH the
    "self-created" and "ever-a-roster-member" queries — must still appear
    exactly once."""
    member = await register(db_session, "mygroups9@example.com", "abc12345")
    member.nickname = "王戊"
    await db_session.commit()
    payload = CreateGroupRequest(
        name="No Duplicate",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    await create_group(db_session, payload, member=member)

    result = await get_my_groups(db_session, member.id)

    assert len(result.groups) == 1


async def test_my_groups_member_status_reflects_most_recent_roster_entry(
    db_session: AsyncSession,
) -> None:
    """A member can leave and rejoin the same group, producing multiple
    historical RosterEntry rows — member_status must reflect the newest
    one (research.md #4), not an arbitrary or earliest row."""
    creator = await register(db_session, "mygroups10@example.com", "abc12345")
    creator.nickname = "團長3"
    joiner = await register(db_session, "mygroups11@example.com", "abc12345")
    joiner.nickname = "團員3"
    await db_session.commit()
    payload = CreateGroupRequest(
        name="Rejoin Group",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, _roster_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=creator
    )
    first_entry, _created_new = await join_group(
        db_session, group, member=joiner, password=None, nickname=None
    )
    await leave_group(
        db_session, group, first_entry.id, guest_session_token=None, member_id=joiner.id
    )
    await join_group(db_session, group, member=joiner, password=None, nickname=None)

    result = await get_my_groups(db_session, joiner.id)

    assert len(result.groups) == 1
    assert result.groups[0].member_status == "active"


async def test_my_groups_excludes_guest_joined_groups(db_session: AsyncSession) -> None:
    creator = await register(db_session, "mygroups12@example.com", "abc12345")
    creator.nickname = "團長4"
    later_registrant = await register(db_session, "mygroups13@example.com", "abc12345")
    later_registrant.nickname = "訪客後來註冊"
    await db_session.commit()
    payload = CreateGroupRequest(
        name="Guest Joined Group",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, _roster_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=creator
    )
    await join_group(db_session, group, member=None, password=None, nickname="訪客小明")

    result = await get_my_groups(db_session, later_registrant.id)

    assert result.groups == []
