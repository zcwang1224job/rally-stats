"""Unit test: logged-in member join path — uses the member's own nickname
(FR-018), requires it to be set first (FR-019), and short-circuits when
already an active member of the group (FR-020a, US6)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import join_group
from app.domains.member.models import Member
from app.domains.member.security import hash_password

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Join As Member Test",
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


async def _make_member(session: AsyncSession, email: str, nickname: str | None) -> Member:
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


async def test_member_with_nickname_joins_using_member_nickname(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    member = await _make_member(db_session, "withname@example.com", "小明")

    roster_entry, created_new = await join_group(
        db_session, group, member=member, password=None, nickname=None
    )
    assert roster_entry.nickname == "小明"
    assert roster_entry.member_id == member.id
    assert roster_entry.guest_session_token is None
    assert created_new is True


async def test_member_without_nickname_is_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    member = await _make_member(db_session, "noname@example.com", None)

    with pytest.raises(ApiError) as exc_info:
        await join_group(db_session, group, member=member, password=None, nickname=None)
    assert exc_info.value.error_code == "MEMBER_NICKNAME_NOT_SET"


async def test_already_active_member_short_circuits(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    member = await _make_member(db_session, "shortcircuit@example.com", "小明")

    first_entry, first_created_new = await join_group(
        db_session, group, member=member, password=None, nickname=None
    )
    assert first_created_new is True

    second_entry, second_created_new = await join_group(
        db_session, group, member=member, password="anything-should-be-ignored", nickname=None
    )
    assert second_created_new is False
    assert second_entry.id == first_entry.id


async def test_already_active_member_short_circuits_even_on_disbanded_group(
    db_session: AsyncSession,
) -> None:
    """005-member-view relies on this: the member view (e.g. Leave Group)
    re-resolves an already-active member's roster_entry_id via join_group(),
    and that read-only short-circuit MUST succeed even on a disbanded group
    (spec Edge Cases) — only a genuinely new join attempt is rejected."""
    group = await _make_group(db_session)
    member = await _make_member(db_session, "disbanded-shortcircuit@example.com", "小明")
    first_entry, _ = await join_group(
        db_session, group, member=member, password=None, nickname=None
    )

    group.status = "disbanded"
    await db_session.commit()

    second_entry, created_new = await join_group(
        db_session, group, member=member, password=None, nickname=None
    )
    assert created_new is False
    assert second_entry.id == first_entry.id


async def test_new_join_attempt_still_rejected_on_disbanded_group(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, status="disbanded")
    member = await _make_member(db_session, "disbanded-newjoin@example.com", "小明")

    with pytest.raises(ApiError) as exc_info:
        await join_group(db_session, group, member=member, password=None, nickname=None)
    assert exc_info.value.error_code == "GROUP_DISBANDED"
