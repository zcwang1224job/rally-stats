"""Unit test: `unlink_oauth_identity()` — contracts/account-recovery-api.md
`DELETE /members/me/oauth-identities/{provider}` (FR-008)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.member.models import Member, MemberOAuthIdentity
from app.domains.member.security import hash_password
from app.domains.member.service import unlink_oauth_identity

pytestmark = pytest.mark.asyncio


async def _make_member(
    session: AsyncSession, email: str, user_number: str, *, with_password: bool = True
) -> Member:
    member = Member(
        email=email,
        password_hash=hash_password("abc12345") if with_password else None,
        user_number=user_number,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def test_unlink_success_removes_the_binding(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "unlink1@example.com", "aB3dEfGh")
    db_session.add(
        MemberOAuthIdentity(member_id=member.id, provider="google", provider_user_id="sub-1")
    )
    await db_session.commit()

    await unlink_oauth_identity(db_session, member, "google")

    remaining = (
        await db_session.execute(
            select(MemberOAuthIdentity).where(MemberOAuthIdentity.member_id == member.id)
        )
    ).scalar_one_or_none()
    assert remaining is None


async def test_unlink_not_linked_raises(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "unlink2@example.com", "cD4eFgHi")

    with pytest.raises(ApiError) as exc_info:
        await unlink_oauth_identity(db_session, member, "google")
    assert exc_info.value.error_code == "OAUTH_IDENTITY_NOT_LINKED"


async def test_unlink_last_login_method_is_refused(db_session: AsyncSession) -> None:
    """FR-008: a password-less member with exactly one binding MUST NOT be
    allowed to remove it."""
    member = await _make_member(db_session, "unlink3@example.com", "eF5gHiJk", with_password=False)
    db_session.add(
        MemberOAuthIdentity(member_id=member.id, provider="google", provider_user_id="sub-3")
    )
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await unlink_oauth_identity(db_session, member, "google")
    assert exc_info.value.error_code == "LAST_LOGIN_METHOD"

    # nothing was deleted
    remaining = (
        await db_session.execute(
            select(MemberOAuthIdentity).where(MemberOAuthIdentity.member_id == member.id)
        )
    ).scalar_one_or_none()
    assert remaining is not None


async def test_unlink_allowed_when_password_still_available(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "unlink4@example.com", "gH6iJkLm", with_password=True)
    db_session.add(
        MemberOAuthIdentity(member_id=member.id, provider="google", provider_user_id="sub-4")
    )
    await db_session.commit()

    await unlink_oauth_identity(db_session, member, "google")

    remaining = (
        await db_session.execute(
            select(MemberOAuthIdentity).where(MemberOAuthIdentity.member_id == member.id)
        )
    ).scalar_one_or_none()
    assert remaining is None


async def test_unlink_allowed_when_another_provider_still_bound(db_session: AsyncSession) -> None:
    member = await _make_member(
        db_session, "unlink5@example.com", "iJ7kLmNo", with_password=False
    )
    db_session.add_all(
        [
            MemberOAuthIdentity(member_id=member.id, provider="google", provider_user_id="sub-5g"),
            MemberOAuthIdentity(member_id=member.id, provider="line", provider_user_id="sub-5l"),
        ]
    )
    await db_session.commit()

    await unlink_oauth_identity(db_session, member, "google")

    remaining = (
        await db_session.execute(
            select(MemberOAuthIdentity).where(MemberOAuthIdentity.member_id == member.id)
        )
    ).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].provider == "line"
