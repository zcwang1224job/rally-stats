"""Unit test: list_friends() applies a nickname/user_number substring
filter (FR-034)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.service import create_friend_request, list_friends, respond_friend_request
from app.domains.member.models import Member
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _verified(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member


async def _become_friends(session: AsyncSession, a: Member, b: Member) -> None:
    created = await create_friend_request(session, a.id, b.user_number)
    await respond_friend_request(session, b.id, uuid.UUID(created.friend_request_id), accept=True)


async def test_friend_list_filters_by_nickname_substring(db_session: AsyncSession) -> None:
    me = await _verified(db_session, "listfilter1@example.com", "我")
    friend_1 = await _verified(db_session, "listfilter2@example.com", "陳小美")
    friend_2 = await _verified(db_session, "listfilter3@example.com", "王大明")
    await _become_friends(db_session, me, friend_1)
    await _become_friends(db_session, me, friend_2)

    result = await list_friends(db_session, me.id, nickname="小美")

    assert len(result.friends) == 1
    assert result.friends[0].nickname == "陳小美"


async def test_friend_list_filters_by_user_number_substring(db_session: AsyncSession) -> None:
    me = await _verified(db_session, "listfilter4@example.com", "我")
    friend_1 = await _verified(db_session, "listfilter5@example.com", "朋友一")
    friend_2 = await _verified(db_session, "listfilter6@example.com", "朋友二")
    await _become_friends(db_session, me, friend_1)
    await _become_friends(db_session, me, friend_2)

    result = await list_friends(db_session, me.id, user_number=friend_1.user_number)

    assert len(result.friends) == 1
    assert result.friends[0].member_id == str(friend_1.id)


async def test_friend_list_shows_both_directions_of_the_relationship(
    db_session: AsyncSession,
) -> None:
    me = await _verified(db_session, "listfilter7@example.com", "我")
    friend = await _verified(db_session, "listfilter8@example.com", "朋友")
    # `friend` is the requester this time — list_friends must still surface
    # them for `me` (the addressee).
    await _become_friends(db_session, friend, me)

    result = await list_friends(db_session, me.id)

    assert len(result.friends) == 1
    assert result.friends[0].member_id == str(friend.id)
