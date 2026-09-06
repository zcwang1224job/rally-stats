"""Unit test: a Member can only be an active RosterEntry in one Group at a
time (new requirement — no spec FR number yet). Deliberately Member-only:
a Guest's RosterEntry has no cross-group identity to check against
(guest_session_token is scoped to a single group by design, FR-022), so
this can't be — and isn't meant to be — enforced for Guests.

Both create_group() and join_group() are covered since creating a group
makes the creator its first (active) RosterEntry — from this rule's
perspective that's just another way of becoming active in a group."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.schemas import CreateGroupRequest
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import create_group, join_group
from app.domains.member.models import Member
from app.domains.member.security import hash_password

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "One Active Group Test",
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


def _create_payload(**overrides: object) -> CreateGroupRequest:
    defaults: dict[str, object] = {
        "name": "Second Group",
        "max_members": 4,
        "match_mode": "doubles",
        "scheduling_mechanism": "manual",
        "turnstile_token": "unused",
    }
    defaults.update(overrides)
    return CreateGroupRequest(**defaults)  # type: ignore[arg-type]


async def test_member_active_elsewhere_cannot_join_a_second_group(
    db_session: AsyncSession,
) -> None:
    group_a = await _make_group(db_session, name="Group A")
    group_b = await _make_group(db_session, name="Group B")
    member = await _make_member(db_session, "activejoin@example.com", "小明")

    await join_group(db_session, group_a, member=member, password=None, nickname=None)

    with pytest.raises(ApiError) as exc_info:
        await join_group(db_session, group_b, member=member, password=None, nickname=None)
    assert exc_info.value.error_code == "ALREADY_ACTIVE_IN_ANOTHER_GROUP"


async def test_member_active_elsewhere_cannot_create_a_second_group(
    db_session: AsyncSession,
) -> None:
    group_a = await _make_group(db_session, name="Group A")
    member = await _make_member(db_session, "activecreate@example.com", "小明")

    await join_group(db_session, group_a, member=member, password=None, nickname=None)

    with pytest.raises(ApiError) as exc_info:
        await create_group(db_session, _create_payload(), member=member)
    assert exc_info.value.error_code == "ALREADY_ACTIVE_IN_ANOTHER_GROUP"


async def test_member_who_left_the_first_group_can_join_a_second(
    db_session: AsyncSession,
) -> None:
    group_a = await _make_group(db_session, name="Group A")
    group_b = await _make_group(db_session, name="Group B")
    member = await _make_member(db_session, "leftfirst@example.com", "小明")

    first_entry, _ = await join_group(
        db_session, group_a, member=member, password=None, nickname=None
    )
    first_entry.status = "left"
    await db_session.commit()

    second_entry, created_new = await join_group(
        db_session, group_b, member=member, password=None, nickname=None
    )
    assert created_new is True
    assert second_entry.group_id == group_b.id


async def test_guest_is_exempt_and_may_join_multiple_groups(db_session: AsyncSession) -> None:
    """No cross-group identity exists for a Guest to check against — this
    is a hard technical limit (FR-022), not a policy choice: two Guest
    joins are indistinguishable from two different people."""
    group_a = await _make_group(db_session, name="Group A")
    group_b = await _make_group(db_session, name="Group B")

    entry_a, created_a = await join_group(
        db_session, group_a, member=None, password=None, nickname="訪客甲"
    )
    entry_b, created_b = await join_group(
        db_session, group_b, member=None, password=None, nickname="訪客甲"
    )
    assert created_a is True
    assert created_b is True
    assert entry_a.group_id == group_a.id
    assert entry_b.group_id == group_b.id
