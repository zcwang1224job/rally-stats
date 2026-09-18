"""Unit test: verify_ever_group_member() — 014 FR-006, regression for
036 research.md Decision 7.

`join_group()` adds a NEW roster row every time a member joins, so a member
who left and came back has two rows in the same group. The check used
`scalar_one_or_none()`, which raises `MultipleResultsFound` on that — a 500
on the group-history endpoints, and on 036's group benchmark which reuses
this check."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.service import verify_ever_group_member
from tests.unit.domains._match_history import make_entry, make_group, make_member

pytestmark = pytest.mark.asyncio


async def test_member_who_left_and_rejoined_passes(db_session: AsyncSession) -> None:
    group = await make_group(db_session)
    member = await make_member(db_session, "rejoin@example.com")
    await make_entry(db_session, group, "first stint", member.id, status="left")
    await make_entry(db_session, group, "second stint", member.id, status="active")

    await verify_ever_group_member(db_session, group.id, member.id)


@pytest.mark.parametrize("status", ["left", "kicked", "active"])
async def test_single_row_of_any_status_passes(db_session: AsyncSession, status: str) -> None:
    group = await make_group(db_session)
    member = await make_member(db_session, f"{status}@example.com")
    await make_entry(db_session, group, "me", member.id, status=status)

    await verify_ever_group_member(db_session, group.id, member.id)


async def test_never_joined_is_refused(db_session: AsyncSession) -> None:
    group = await make_group(db_session)
    member = await make_member(db_session, "stranger@example.com")

    with pytest.raises(ApiError) as excinfo:
        await verify_ever_group_member(db_session, group.id, member.id)
    assert excinfo.value.error_code == "GROUP_MEMBERSHIP_NEVER_HELD"
    assert excinfo.value.status_code == 403


async def test_guest_rows_do_not_count(db_session: AsyncSession) -> None:
    group = await make_group(db_session)
    member = await make_member(db_session, "guestonly@example.com")
    await make_entry(db_session, group, "a guest", None)

    with pytest.raises(ApiError) as excinfo:
        await verify_ever_group_member(db_session, group.id, member.id)
    assert excinfo.value.error_code == "GROUP_MEMBERSHIP_NEVER_HELD"
