"""Unit test: join_group()'s skip_password parameter (013-group-invite-friends,
FR-007/Clarifications Q1). Defaults to False — a regression check that every
pre-existing caller's password enforcement is completely unaffected."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import encrypt_group_password, hash_admin_pin
from app.domains.group.service import join_group
from app.domains.member.models import Member
from app.domains.member.security import hash_password

pytestmark = pytest.mark.asyncio


async def _make_group_with_password(session: AsyncSession, password: str) -> Group:
    ciphertext, nonce = encrypt_group_password(password)
    group = Group(
        name="Skip Password Test",
        password_ciphertext=ciphertext,
        password_nonce=nonce,
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


async def test_skip_password_true_bypasses_correct_password_requirement(
    db_session: AsyncSession,
) -> None:
    group = await _make_group_with_password(db_session, "secret123")
    member = await _make_member(db_session, "skip1@example.com", "小明")

    roster_entry, created_new = await join_group(
        db_session, group, member=member, password=None, nickname=None, skip_password=True
    )
    assert created_new is True
    assert roster_entry.member_id == member.id


async def test_skip_password_default_false_still_enforces_password(
    db_session: AsyncSession,
) -> None:
    group = await _make_group_with_password(db_session, "secret123")
    member = await _make_member(db_session, "skip2@example.com", "小華")

    with pytest.raises(ApiError) as exc_info:
        await join_group(db_session, group, member=member, password=None, nickname=None)
    assert exc_info.value.error_code == "GROUP_PASSWORD_INCORRECT"


async def test_skip_password_explicit_false_still_enforces_password(
    db_session: AsyncSession,
) -> None:
    group = await _make_group_with_password(db_session, "secret123")
    member = await _make_member(db_session, "skip3@example.com", "小美")

    with pytest.raises(ApiError) as exc_info:
        await join_group(
            db_session, group, member=member, password="wrong", nickname=None, skip_password=False
        )
    assert exc_info.value.error_code == "GROUP_PASSWORD_INCORRECT"


async def test_correct_password_still_works_without_skip(db_session: AsyncSession) -> None:
    group = await _make_group_with_password(db_session, "secret123")
    member = await _make_member(db_session, "skip4@example.com", "小強")

    roster_entry, created_new = await join_group(
        db_session, group, member=member, password="secret123", nickname=None
    )
    assert created_new is True
    assert roster_entry.member_id == member.id
