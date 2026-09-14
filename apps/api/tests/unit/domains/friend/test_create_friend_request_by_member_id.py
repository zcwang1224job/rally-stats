"""Unit tests for create_friend_request_by_member_id() — the
026-match-record-friend-invite US1 send action. Shares every rule with the
existing user_number-based create_friend_request() via the extracted
_create_friend_request_for_addressee() core (FR-005); the only new rule
here is addressing by member_id, including a Guest-only roster id having no
Member row at all."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.friend.service import (
    create_friend_request_by_member_id,
    get_friendship_status,
    respond_friend_request,
)
from app.domains.member.models import Member
from app.domains.member.service import delete_account, register

pytestmark = pytest.mark.asyncio


async def _verified(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member


async def test_success_creates_pending_request(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "bymid-a1@example.com", "A")
    b = await _verified(db_session, "bymid-b1@example.com", "B")

    created = await create_friend_request_by_member_id(db_session, a.id, b.id)

    assert created.status == "pending"
    assert await get_friendship_status(db_session, a.id, b.id) == "pending_outgoing"


async def test_nonexistent_member_id_raises_member_not_found(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "bymid-a2@example.com", "A")

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request_by_member_id(db_session, a.id, uuid.uuid4())
    assert exc_info.value.error_code == "MEMBER_NOT_FOUND"


async def test_guest_only_roster_id_raises_member_not_found(db_session: AsyncSession) -> None:
    """A Guest has no Member row at all — a client that somehow sent a
    Guest's roster_entry_id (or any other non-Member uuid) as
    addressee_member_id MUST get the same MEMBER_NOT_FOUND as a genuinely
    nonexistent id, not a different/leaky error."""
    a = await _verified(db_session, "bymid-a3@example.com", "A")

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request_by_member_id(db_session, a.id, uuid.uuid4())
    assert exc_info.value.error_code == "MEMBER_NOT_FOUND"


async def test_unverified_member_raises_member_not_found(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "bymid-a4@example.com", "A")
    unverified = await register(db_session, "bymid-b4@example.com", "abc12345")

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request_by_member_id(db_session, a.id, unverified.id)
    assert exc_info.value.error_code == "MEMBER_NOT_FOUND"


async def test_deleted_member_raises_member_not_found(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "bymid-a5@example.com", "A")
    b = await _verified(db_session, "bymid-b5@example.com", "B")
    await delete_account(db_session, b, "abc12345")

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request_by_member_id(db_session, a.id, b.id)
    assert exc_info.value.error_code == "MEMBER_NOT_FOUND"


async def test_cannot_friend_self(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "bymid-a6@example.com", "A")

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request_by_member_id(db_session, a.id, a.id)
    assert exc_info.value.error_code == "CANNOT_FRIEND_SELF"


async def test_already_friends(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "bymid-a7@example.com", "A")
    b = await _verified(db_session, "bymid-b7@example.com", "B")
    created = await create_friend_request_by_member_id(db_session, a.id, b.id)
    await respond_friend_request(
        db_session, b.id, uuid.UUID(created.friend_request_id), accept=True
    )

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request_by_member_id(db_session, a.id, b.id)
    assert exc_info.value.error_code == "ALREADY_FRIENDS"


async def test_already_pending(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "bymid-a8@example.com", "A")
    b = await _verified(db_session, "bymid-b8@example.com", "B")
    await create_friend_request_by_member_id(db_session, a.id, b.id)

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request_by_member_id(db_session, a.id, b.id)
    assert exc_info.value.error_code == "FRIEND_REQUEST_ALREADY_PENDING"


# --- 026-match-record-friend-invite US3 (T041): allow_friend_invite_from_match_pages ---


async def test_rejects_when_target_toggle_off_and_no_relationship(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "bymid-a9@example.com", "A")
    b = await _verified(db_session, "bymid-b9@example.com", "B")
    b.allow_friend_invite_from_match_pages = False
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request_by_member_id(db_session, a.id, b.id)
    assert exc_info.value.error_code == "INVITE_VIA_MATCH_PAGES_NOT_ALLOWED"


async def test_toggle_off_does_not_block_when_already_friends(db_session: AsyncSession) -> None:
    """FR-009: the toggle only gates the `none` case — once a relationship
    already exists, turning it off later MUST NOT retroactively block the
    (already-successful) existing-relationship error paths."""
    a = await _verified(db_session, "bymid-a10@example.com", "A")
    b = await _verified(db_session, "bymid-b10@example.com", "B")
    created = await create_friend_request_by_member_id(db_session, a.id, b.id)
    await respond_friend_request(
        db_session, b.id, uuid.UUID(created.friend_request_id), accept=True
    )
    b.allow_friend_invite_from_match_pages = False
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request_by_member_id(db_session, a.id, b.id)
    assert exc_info.value.error_code == "ALREADY_FRIENDS"


async def test_toggle_off_does_not_block_when_already_pending(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "bymid-a11@example.com", "A")
    b = await _verified(db_session, "bymid-b11@example.com", "B")
    await create_friend_request_by_member_id(db_session, a.id, b.id)
    b.allow_friend_invite_from_match_pages = False
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request_by_member_id(db_session, a.id, b.id)
    assert exc_info.value.error_code == "FRIEND_REQUEST_ALREADY_PENDING"


async def test_toggle_on_succeeds(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "bymid-a12@example.com", "A")
    b = await _verified(db_session, "bymid-b12@example.com", "B")
    assert b.allow_friend_invite_from_match_pages is True

    created = await create_friend_request_by_member_id(db_session, a.id, b.id)
    assert created.status == "pending"
