"""Unit test: verify_password() — correct/incorrect comparison, no lockout
(FR-016)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import encrypt_group_password, hash_admin_pin
from app.domains.group.service import verify_password

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, password: str | None) -> Group:
    ciphertext, nonce = (None, None)
    if password is not None:
        ciphertext, nonce = encrypt_group_password(password)
    group = Group(
        name="Verify Password Test",
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


async def test_verify_password_correct(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, "secret123")
    assert verify_password(group, "secret123") is True


async def test_verify_password_incorrect(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, "secret123")
    assert verify_password(group, "wrong-password") is False


async def test_verify_password_group_without_password_always_correct(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, None)
    assert verify_password(group, "anything") is True


async def test_verify_password_repeated_wrong_attempts_never_lock(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, "secret123")
    for _ in range(15):
        assert verify_password(group, "wrong-password") is False
    # Still succeeds afterward — no lockout state was ever introduced.
    assert verify_password(group, "secret123") is True
