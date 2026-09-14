"""Unit tests for `delete_account()` (025-delete-account).

FR-002/FR-003/FR-003a/FR-004/FR-005: requires the correct current password;
overwrites email/password_hash/nickname with placeholders; sets `deleted_at`;
bumps `token_version`; cascades the placeholder nickname to every
`roster_entries` row for this member regardless of match/round status
(the one deliberate exception to the 006 nickname-snapshot-isolation
precedent — see `test_nickname_snapshot_isolation.py`); invalidates every
unused verification/password-reset token for this member, leaving
already-used ones untouched."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.member.models import EmailVerificationToken, PasswordResetToken
from app.domains.member.security import verify_password
from app.domains.member.service import (
    DELETED_MEMBER_PLACEHOLDER_NICKNAME,
    delete_account,
    forgot_password,
    register,
)
from app.domains.roster.models import RosterEntry

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Delete Account Test",
        max_members=4,
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


async def test_delete_account_rejects_wrong_password(db_session: AsyncSession) -> None:
    member = await register(db_session, "delacc-wrong@example.com", "abc12345")
    original_email = member.email

    with pytest.raises(ApiError) as exc_info:
        await delete_account(db_session, member, "wrong-password")
    assert exc_info.value.error_code == "CURRENT_PASSWORD_INCORRECT"

    await db_session.refresh(member)
    assert member.email == original_email
    assert member.deleted_at is None


async def test_delete_account_overwrites_pii_and_marks_deleted(db_session: AsyncSession) -> None:
    member = await register(db_session, "delacc1@example.com", "abc12345")
    member.nickname = "真實姓名"
    await db_session.commit()
    starting_version = member.token_version

    updated = await delete_account(db_session, member, "abc12345")

    assert updated.email != "delacc1@example.com"
    assert str(updated.id) in updated.email
    assert not verify_password("abc12345", updated.password_hash)
    assert updated.nickname == DELETED_MEMBER_PLACEHOLDER_NICKNAME
    assert updated.deleted_at is not None
    assert updated.token_version == starting_version + 1


async def test_delete_account_cascades_placeholder_to_all_roster_statuses(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "delacc2@example.com", "abc12345")
    group = await _make_group(db_session)
    queued = RosterEntry(
        group_id=group.id, member_id=member.id, nickname="真實姓名", status="active"
    )
    in_progress = RosterEntry(
        group_id=group.id, member_id=member.id, nickname="真實姓名2", status="active"
    )
    left = RosterEntry(
        group_id=group.id, member_id=member.id, nickname="真實姓名3", status="left"
    )
    db_session.add_all([queued, in_progress, left])
    await db_session.commit()

    await delete_account(db_session, member, "abc12345")

    for entry in (queued, in_progress, left):
        await db_session.refresh(entry)
        assert entry.nickname == DELETED_MEMBER_PLACEHOLDER_NICKNAME


async def test_delete_account_does_not_touch_other_members_roster_entries(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "delacc3@example.com", "abc12345")
    other = await register(db_session, "delacc3-other@example.com", "abc12345")
    group = await _make_group(db_session)
    other_entry = RosterEntry(
        group_id=group.id, member_id=other.id, nickname="別人的暱稱", status="active"
    )
    db_session.add(other_entry)
    await db_session.commit()

    await delete_account(db_session, member, "abc12345")

    await db_session.refresh(other_entry)
    assert other_entry.nickname == "別人的暱稱"


async def test_delete_account_invalidates_unused_tokens_but_not_used_ones(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "delacc4@example.com", "abc12345")
    await forgot_password(db_session, "delacc4@example.com")

    verification_result = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
    )
    verification_token = verification_result.scalar_one()
    reset_result = await db_session.execute(
        select(PasswordResetToken).where(PasswordResetToken.member_id == member.id)
    )
    reset_token = reset_result.scalar_one()

    already_used = PasswordResetToken(
        member_id=member.id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        used_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(already_used)
    await db_session.commit()

    await delete_account(db_session, member, "abc12345")

    await db_session.refresh(verification_token)
    await db_session.refresh(reset_token)
    await db_session.refresh(already_used)
    assert verification_token.used_at is not None
    assert reset_token.used_at is not None
    # Already-used token's original used_at timestamp is left alone, not
    # bumped to "now" — confirms it wasn't blindly overwritten.
    assert already_used.used_at < datetime.now(UTC) - timedelta(minutes=4)
