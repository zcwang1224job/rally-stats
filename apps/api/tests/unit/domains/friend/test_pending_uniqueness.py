"""Unit test: at most one pending friend request per pair, regardless of
direction (FR-039) — the DB's own partial unique index surfaces as
FRIEND_REQUEST_ALREADY_PENDING, and the pre-check catches the same case
before ever reaching the DB."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.friend.models import FriendRequest
from app.domains.friend.service import create_friend_request
from app.domains.member.models import Member
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _verified(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member


async def test_second_request_same_direction_is_rejected(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "pending1a@example.com", "A")
    b = await _verified(db_session, "pending1b@example.com", "B")
    await create_friend_request(db_session, a.id, b.user_number)

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request(db_session, a.id, b.user_number)
    assert exc_info.value.error_code == "FRIEND_REQUEST_ALREADY_PENDING"


async def test_reverse_direction_request_is_also_rejected(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "pending2a@example.com", "A")
    b = await _verified(db_session, "pending2b@example.com", "B")
    await create_friend_request(db_session, a.id, b.user_number)

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request(db_session, b.id, a.user_number)
    assert exc_info.value.error_code == "FRIEND_REQUEST_ALREADY_PENDING"


async def test_db_partial_unique_index_enforces_the_same_rule_directly(
    db_session: AsyncSession,
) -> None:
    """Bypasses the service-layer pre-check entirely to prove the DB
    constraint itself (not just application logic) enforces the rule."""
    a = await _verified(db_session, "pending3a@example.com", "A")
    b = await _verified(db_session, "pending3b@example.com", "B")
    db_session.add(FriendRequest(requester_id=a.id, addressee_id=b.id))
    await db_session.commit()

    db_session.add(FriendRequest(requester_id=b.id, addressee_id=a.id))
    with pytest.raises(Exception):  # noqa: B017 - asserting the raw DB IntegrityError surfaces
        await db_session.commit()
