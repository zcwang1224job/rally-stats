"""Unit test: change_password() requires the correct current_password,
bumps token_version (invalidating other devices), and returns a fresh token
pair for the requesting device (FR-025/026)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.member.security import require_member, verify_password
from app.domains.member.service import change_password, register

pytestmark = pytest.mark.asyncio


async def test_change_password_rejects_wrong_current_password(db_session: AsyncSession) -> None:
    member = await register(db_session, "changepw@example.com", "abc12345")

    with pytest.raises(ApiError) as exc_info:
        await change_password(db_session, member, "wrong-current", "newpass123")
    assert exc_info.value.error_code == "CURRENT_PASSWORD_INCORRECT"


async def test_change_password_updates_hash_and_bumps_token_version(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "changepw2@example.com", "abc12345")
    starting_version = member.token_version

    updated_member, _access, _refresh = await change_password(
        db_session, member, "abc12345", "newpass123"
    )

    assert verify_password("newpass123", updated_member.password_hash)
    assert updated_member.token_version == starting_version + 1


async def test_change_password_issues_valid_token_for_current_device(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "changepw3@example.com", "abc12345")

    _member, access_token, _refresh = await change_password(
        db_session, member, "abc12345", "newpass123"
    )

    resolved = await require_member(authorization=f"Bearer {access_token}", session=db_session)
    assert resolved.id == member.id
