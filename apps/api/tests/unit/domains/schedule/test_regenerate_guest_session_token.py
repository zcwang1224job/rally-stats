"""Unit test: regenerate_guest_session_token — constitution IV requires
every link-type token to be independently regenerable by the admin."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.member.models import Member
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import regenerate_guest_session_token

pytestmark = pytest.mark.asyncio


async def _make_member(session: AsyncSession, email: str) -> Member:
    member = Member(
        email=email,
        password_hash="x",
        nickname="會員小華",
        user_number=str(uuid.uuid4())[:8],
        verification_status="verified",
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Regen Guest Token Test",
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


async def _make_entry(
    session: AsyncSession,
    group: Group,
    *,
    member_id: uuid.UUID | None = None,
    status: str = "active",
    guest_session_token: str | None = "old-token",
) -> RosterEntry:
    entry = RosterEntry(
        group_id=group.id,
        nickname="小明",
        member_id=member_id,
        status=status,
        guest_session_token=guest_session_token,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def test_regenerate_issues_a_different_token(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry = await _make_entry(db_session, group)

    updated = await regenerate_guest_session_token(db_session, group, entry)

    assert updated.guest_session_token is not None
    assert updated.guest_session_token != "old-token"


async def test_rejects_a_roster_entry_from_a_different_group(db_session: AsyncSession) -> None:
    group_a = await _make_group(db_session)
    group_b = await _make_group(db_session)
    entry = await _make_entry(db_session, group_a)

    with pytest.raises(ApiError) as exc_info:
        await regenerate_guest_session_token(db_session, group_b, entry)
    assert exc_info.value.error_code == "ROSTER_ENTRY_NOT_FOUND"


async def test_rejects_a_member_entry(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    member = await _make_member(db_session, "regen-guest-token-unit@example.com")
    entry = await _make_entry(db_session, group, member_id=member.id)

    with pytest.raises(ApiError) as exc_info:
        await regenerate_guest_session_token(db_session, group, entry)
    assert exc_info.value.error_code == "NOT_A_GUEST_ENTRY"


async def test_rejects_an_entry_that_already_left(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry = await _make_entry(db_session, group, status="left")

    with pytest.raises(ApiError) as exc_info:
        await regenerate_guest_session_token(db_session, group, entry)
    assert exc_info.value.error_code == "ROSTER_ENTRY_ALREADY_LEFT"
