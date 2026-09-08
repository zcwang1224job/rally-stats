"""Unit test: verify_ever_group_member() — 014-member-groups-history FR-006
(Clarifications 2026-09-07). Deliberately independent of
resolve_active_roster_membership()."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.schemas import CreateGroupRequest
from app.domains.group.service import (
    create_group,
    join_group,
    leave_group,
    verify_ever_group_member,
)
from app.domains.member.models import Member
from app.domains.member.security import hash_password

pytestmark = pytest.mark.asyncio


async def _make_member(session: AsyncSession, email: str, nickname: str) -> Member:
    member = Member(
        email=email,
        password_hash=hash_password("abc12345"),
        user_number=email[:8].upper().ljust(8, "A"),
        nickname=nickname,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def test_passes_for_creators_own_entry(db_session: AsyncSession) -> None:
    creator = await _make_member(db_session, "verify-a1@example.com", "A")
    payload = CreateGroupRequest(
        name="Verify Group 1",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, _roster_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=creator
    )

    await verify_ever_group_member(db_session, group.id, creator.id)  # must not raise


async def test_passes_for_active_joined_member(db_session: AsyncSession) -> None:
    creator = await _make_member(db_session, "verify-a2@example.com", "A")
    joiner = await _make_member(db_session, "verify-b2@example.com", "B")
    payload = CreateGroupRequest(
        name="Verify Group 2",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, _roster_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=creator
    )
    await join_group(db_session, group, member=joiner, password=None, nickname=None)

    await verify_ever_group_member(db_session, group.id, joiner.id)  # must not raise


async def test_passes_for_member_who_has_left(db_session: AsyncSession) -> None:
    creator = await _make_member(db_session, "verify-a3@example.com", "A")
    joiner = await _make_member(db_session, "verify-b3@example.com", "B")
    payload = CreateGroupRequest(
        name="Verify Group 3",
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

    await verify_ever_group_member(db_session, group.id, joiner.id)  # must not raise


async def test_rejects_member_who_was_never_in_the_group(db_session: AsyncSession) -> None:
    creator = await _make_member(db_session, "verify-a4@example.com", "A")
    stranger = await _make_member(db_session, "verify-c4@example.com", "C")
    payload = CreateGroupRequest(
        name="Verify Group 4",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, _roster_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=creator
    )

    with pytest.raises(ApiError) as exc_info:
        await verify_ever_group_member(db_session, group.id, stranger.id)
    assert exc_info.value.error_code == "GROUP_MEMBERSHIP_NEVER_HELD"


async def test_does_not_loosen_resolve_active_roster_membership(db_session: AsyncSession) -> None:
    """Regression guard: this new function must be a genuinely separate
    check, not a relaxation of resolve_active_roster_membership() — a
    former (left) member must still fail THAT function's stricter
    "currently active" requirement even though verify_ever_group_member()
    passes for them."""
    from app.domains.group.service import resolve_active_roster_membership

    creator = await _make_member(db_session, "verify-a5@example.com", "A")
    joiner = await _make_member(db_session, "verify-b5@example.com", "B")
    payload = CreateGroupRequest(
        name="Verify Group 5",
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

    await verify_ever_group_member(db_session, group.id, joiner.id)  # passes

    with pytest.raises(ApiError) as exc_info:
        await resolve_active_roster_membership(
            db_session, group.id, guest_session_token=None, member_id=joiner.id
        )
    assert exc_info.value.error_code == "MEMBERSHIP_REQUIRED"
