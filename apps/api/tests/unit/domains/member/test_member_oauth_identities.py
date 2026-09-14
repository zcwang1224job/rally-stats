"""Unit test: `member_oauth_identities`'s two UNIQUE constraints
(data-model.md §2) — the DB-level backstop behind FR-006/FR-007's
application-layer checks."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member, MemberOAuthIdentity
from app.domains.member.security import hash_password

pytestmark = pytest.mark.asyncio


async def _make_member(session: AsyncSession, email: str, user_number: str) -> Member:
    member = Member(email=email, password_hash=hash_password("abc12345"), user_number=user_number)
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def test_same_external_account_cannot_link_two_members(db_session: AsyncSession) -> None:
    """FR-007: UNIQUE(provider, provider_user_id)."""
    a = await _make_member(db_session, "oauth-a@example.com", "aB3dEfGh")
    b = await _make_member(db_session, "oauth-b@example.com", "cD4eFgHi")

    db_session.add(MemberOAuthIdentity(member_id=a.id, provider="google", provider_user_id="sub-1"))
    await db_session.commit()

    db_session.add(MemberOAuthIdentity(member_id=b.id, provider="google", provider_user_id="sub-1"))
    with pytest.raises(Exception):  # noqa: B017 - asserting the raw DB IntegrityError surfaces
        await db_session.commit()


async def test_one_member_cannot_bind_two_accounts_for_the_same_provider(
    db_session: AsyncSession,
) -> None:
    """FR-006: UNIQUE(member_id, provider)."""
    a = await _make_member(db_session, "oauth-c@example.com", "eF5gHiJk")

    db_session.add(MemberOAuthIdentity(member_id=a.id, provider="google", provider_user_id="sub-2"))
    await db_session.commit()

    db_session.add(MemberOAuthIdentity(member_id=a.id, provider="google", provider_user_id="sub-3"))
    with pytest.raises(Exception):  # noqa: B017 - asserting the raw DB IntegrityError surfaces
        await db_session.commit()


async def test_same_member_can_bind_different_providers(db_session: AsyncSession) -> None:
    a = await _make_member(db_session, "oauth-d@example.com", "gH6iJkLm")

    db_session.add(MemberOAuthIdentity(member_id=a.id, provider="google", provider_user_id="sub-4"))
    db_session.add(MemberOAuthIdentity(member_id=a.id, provider="line", provider_user_id="sub-5"))
    await db_session.commit()
