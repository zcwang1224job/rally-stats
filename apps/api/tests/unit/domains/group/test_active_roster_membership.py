"""Unit test: resolve_active_roster_membership() — Guest token or Member
identity, whichever is provided, must resolve to an `active` RosterEntry in
this group; missing/invalid/non-active always fails the same way
(`MEMBERSHIP_REQUIRED`, 403), and disbanded groups are NOT excluded
(005-member-view research.md #5 — unlike resolve_guest_session())."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import join_group, resolve_active_roster_membership
from app.domains.member.models import Member

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Membership Test",
        "max_members": 8,
        "match_mode": "doubles",
        "scheduling_mechanism": "manual",
        "current_member_count": 1,
        "status": "active",
        "admin_pin_hash": hash_admin_pin("111111"),
    }
    defaults.update(overrides)
    group = Group(**defaults)  # type: ignore[arg-type]
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_member(session: AsyncSession) -> Member:
    member = Member(
        email=f"{uuid.uuid4()}@example.com",
        password_hash="x",
        nickname="小明",
        user_number=str(uuid.uuid4())[:8],
        verification_status="verified",
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def test_guest_token_active_entry_resolves(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry, _ = await join_group(db_session, group, member=None, password=None, nickname="小美")

    resolved = await resolve_active_roster_membership(
        db_session, group.id, guest_session_token=entry.guest_session_token, member_id=None
    )
    assert resolved.id == entry.id


async def test_guest_token_non_active_entry_raises(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry, _ = await join_group(db_session, group, member=None, password=None, nickname="小美")
    entry.status = "left"
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await resolve_active_roster_membership(
            db_session, group.id, guest_session_token=entry.guest_session_token, member_id=None
        )
    assert exc_info.value.error_code == "MEMBERSHIP_REQUIRED"
    assert exc_info.value.status_code == 403


async def test_unknown_guest_token_raises(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)

    with pytest.raises(ApiError) as exc_info:
        await resolve_active_roster_membership(
            db_session, group.id, guest_session_token="not-a-real-token", member_id=None
        )
    assert exc_info.value.error_code == "MEMBERSHIP_REQUIRED"


async def test_member_with_active_entry_resolves(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    member = await _make_member(db_session)
    entry, _ = await join_group(db_session, group, member=member, password=None, nickname="小明")

    resolved = await resolve_active_roster_membership(
        db_session, group.id, guest_session_token=None, member_id=member.id
    )
    assert resolved.id == entry.id


async def test_member_without_active_entry_raises(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    member = await _make_member(db_session)

    with pytest.raises(ApiError) as exc_info:
        await resolve_active_roster_membership(
            db_session, group.id, guest_session_token=None, member_id=member.id
        )
    assert exc_info.value.error_code == "MEMBERSHIP_REQUIRED"


async def test_neither_guest_token_nor_member_raises(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)

    with pytest.raises(ApiError) as exc_info:
        await resolve_active_roster_membership(
            db_session, group.id, guest_session_token=None, member_id=None
        )
    assert exc_info.value.error_code == "MEMBERSHIP_REQUIRED"


async def test_disbanded_group_still_resolves(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry, _ = await join_group(db_session, group, member=None, password=None, nickname="小美")
    group.status = "disbanded"
    await db_session.commit()

    resolved = await resolve_active_roster_membership(
        db_session, group.id, guest_session_token=entry.guest_session_token, member_id=None
    )
    assert resolved.id == entry.id
