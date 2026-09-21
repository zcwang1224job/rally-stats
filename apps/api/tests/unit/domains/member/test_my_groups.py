"""Unit test: get_my_groups() — originally only returned groups created by
the caller (FR-028/029); 014-member-groups-history extends it to the union
of self-created ∪ ever-a-roster-member groups (any status), each annotated
with is_creator/member_status (FR-001~003)."""

import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

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
    assert result.groups[0].disbanded_at is not None


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
    assert result.groups[0].created_at is not None
    assert result.groups[0].disbanded_at is None


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


def _group_payload(name: str) -> CreateGroupRequest:
    return CreateGroupRequest(
        name=name,
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )


async def _my_group_names(session: AsyncSession, member_id: uuid.UUID, **filters: Any) -> set[str]:
    return {group.name for group in (await get_my_groups(session, member_id, **filters)).groups}


async def test_my_groups_filters_by_name_number_role_status_and_group_id(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "mygroups14@example.com", "abc12345")
    member.nickname = "篩選者"
    other = await register(db_session, "mygroups15@example.com", "abc12345")
    other.nickname = "別的團長"
    await db_session.commit()

    # A member can only be active in one group at a time, so each earlier
    # group is disbanded/left before the next one starts.
    disbanded, *_ = await create_group(db_session, _group_payload("Old Weekend"), member=member)
    await disband_group(db_session, disbanded)
    joined, *_ = await create_group(db_session, _group_payload("Friday Club"), member=other)
    roster_entry, _created_new = await join_group(
        db_session, joined, member=member, password=None, nickname=None
    )
    await leave_group(
        db_session, joined, roster_entry.id, guest_session_token=None, member_id=member.id
    )
    created, *_ = await create_group(db_session, _group_payload("Wednesday Night"), member=member)

    assert await _my_group_names(db_session, member.id) == {
        "Wednesday Night",
        "Old Weekend",
        "Friday Club",
    }
    # name: case-insensitive substring
    assert await _my_group_names(db_session, member.id, name="wEEk") == {"Old Weekend"}
    # group_number: substring of the number's digits
    assert await _my_group_names(
        db_session, member.id, group_number=str(joined.group_number)
    ) == {"Friday Club"}
    assert await _my_group_names(db_session, member.id, role="creator") == {
        "Wednesday Night",
        "Old Weekend",
    }
    assert await _my_group_names(db_session, member.id, role="member") == {"Friday Club"}
    assert await _my_group_names(db_session, member.id, group_id=created.id) == {
        "Wednesday Night"
    }
    # filters combine with AND
    assert await _my_group_names(db_session, member.id, role="creator", name="night") == {
        "Wednesday Night"
    }
    no_match = await get_my_groups(db_session, member.id, name="nothing like this")
    assert no_match.groups == []
    assert no_match.total_pages == 1


async def test_my_groups_filters_by_created_and_disbanded_time_ranges(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "mygroups17@example.com", "abc12345")
    member.nickname = "時間篩選者"
    await db_session.commit()
    taipei = timezone(timedelta(hours=8))

    # Opened 9/21 07:30 Taipei time — which is still 9/20 in UTC.
    early, *_ = await create_group(db_session, _group_payload("Early Bird"), member=member)
    await disband_group(db_session, early)
    early.created_at = datetime(2026, 9, 20, 23, 30, tzinfo=UTC)
    early.disbanded_at = datetime(2026, 9, 25, 10, 0, tzinfo=UTC)
    late, *_ = await create_group(db_session, _group_payload("Still Going"), member=member)
    late.created_at = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    await db_session.commit()

    def day(month: int, date_: int) -> datetime:
        return datetime(2026, month, date_, tzinfo=taipei)

    # The viewer's LOCAL day decides, not the UTC date.
    assert await _my_group_names(
        db_session, member.id, created_from=day(9, 21), created_before=day(9, 22)
    ) == {"Early Bird"}
    assert (
        await _my_group_names(
            db_session, member.id, created_from=day(9, 20), created_before=day(9, 21)
        )
        == set()
    )
    # open-ended on either side
    assert await _my_group_names(db_session, member.id, created_from=day(9, 22)) == {
        "Still Going"
    }
    assert await _my_group_names(db_session, member.id, created_before=day(9, 22)) == {
        "Early Bird"
    }
    # `from` is inclusive, `before` is exclusive
    assert await _my_group_names(db_session, member.id, created_from=early.created_at) == {
        "Early Bird",
        "Still Going",
    }
    assert await _my_group_names(db_session, member.id, created_before=early.created_at) == set()

    # Any disbanded bound drops a group with no disbanded_at.
    assert await _my_group_names(db_session, member.id, disbanded_from=day(9, 1)) == {
        "Early Bird"
    }
    assert await _my_group_names(db_session, member.id, disbanded_before=day(12, 31)) == {
        "Early Bird"
    }
    assert (
        await _my_group_names(
            db_session, member.id, disbanded_from=day(9, 26), disbanded_before=day(9, 27)
        )
        == set()
    )
    # both ranges together
    assert await _my_group_names(
        db_session,
        member.id,
        created_from=day(9, 21),
        created_before=day(9, 22),
        disbanded_from=day(9, 25),
        disbanded_before=day(9, 26),
    ) == {"Early Bird"}


async def test_my_groups_paginates_newest_first(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _page_size_two(_session: AsyncSession) -> int:
        return 2

    monkeypatch.setattr("app.domains.member.service.get_default_page_size", _page_size_two)
    member = await register(db_session, "mygroups16@example.com", "abc12345")
    member.nickname = "分頁者"
    await db_session.commit()
    for index in range(5):
        # one active group at a time: disband each before creating the next
        group, *_ = await create_group(db_session, _group_payload(f"Paged {index}"), member=member)
        await disband_group(db_session, group)

    first = await get_my_groups(db_session, member.id)
    third = await get_my_groups(db_session, member.id, page=3)
    beyond = await get_my_groups(db_session, member.id, page=9)

    assert (first.page, first.total_pages) == (1, 3)
    assert [g.name for g in first.groups] == ["Paged 4", "Paged 3"]
    assert [g.name for g in third.groups] == ["Paged 0"]
    assert (beyond.groups, beyond.total_pages) == ([], 3)

    # a filter narrows the set BEFORE paging, so total_pages follows it
    filtered = await get_my_groups(db_session, member.id, name="Paged 1")
    assert [g.name for g in filtered.groups] == ["Paged 1"]
    assert filtered.total_pages == 1
