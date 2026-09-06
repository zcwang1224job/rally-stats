"""Friend domain service layer: search, requests, accept/reject, unfriend.
Per specs/006-member-friends/plan.md."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.friend.models import FriendRequest
from app.domains.friend.schemas import (
    FriendListResponse,
    FriendRequestResponse,
    FriendSummary,
    IncomingFriendRequest,
    IncomingFriendRequestsResponse,
)
from app.domains.member.models import Member

_FRIEND_LIST_PAGE_SIZE = 20


async def get_friendship_status(
    session: AsyncSession, member_a: uuid.UUID, member_b: uuid.UUID
) -> str:
    """FR-038: the four-state relationship between two members, from
    `member_a`'s point of view. Also used by `member/service.py`'s
    `search_member` — kept here (not duplicated) since it's this domain's
    own state machine (data-model.md §4)."""
    result = await session.execute(
        select(FriendRequest)
        .where(
            or_(
                and_(
                    FriendRequest.requester_id == member_a,
                    FriendRequest.addressee_id == member_b,
                ),
                and_(
                    FriendRequest.requester_id == member_b,
                    FriendRequest.addressee_id == member_a,
                ),
            ),
            FriendRequest.status.in_(("pending", "accepted")),
        )
        .order_by(FriendRequest.updated_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return "none"
    if row.status == "accepted":
        return "friends"
    return "pending_outgoing" if row.requester_id == member_a else "pending_incoming"


async def create_friend_request(
    session: AsyncSession, requester_id: uuid.UUID, addressee_user_number: str
) -> FriendRequestResponse:
    """Errors: `MEMBER_NOT_FOUND` (FR-036, unverified accounts included),
    `CANNOT_FRIEND_SELF` (FR-037), `FRIEND_REQUEST_ALREADY_PENDING` (FR-039,
    either from the pre-check or the DB's own partial unique index),
    `ALREADY_FRIENDS`."""
    result = await session.execute(
        select(Member).where(func.lower(Member.user_number) == addressee_user_number.lower())
    )
    addressee = result.scalar_one_or_none()
    if addressee is None or addressee.verification_status != "verified":
        raise ApiError("MEMBER_NOT_FOUND", status_code=404)
    if addressee.id == requester_id:
        raise ApiError("CANNOT_FRIEND_SELF", status_code=400)

    status = await get_friendship_status(session, requester_id, addressee.id)
    if status == "friends":
        raise ApiError("ALREADY_FRIENDS", status_code=409)
    if status in ("pending_outgoing", "pending_incoming"):
        raise ApiError("FRIEND_REQUEST_ALREADY_PENDING", status_code=409)

    friend_request = FriendRequest(requester_id=requester_id, addressee_id=addressee.id)
    session.add(friend_request)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ApiError("FRIEND_REQUEST_ALREADY_PENDING", status_code=409) from None
    await session.refresh(friend_request)
    return FriendRequestResponse(
        friend_request_id=str(friend_request.id), status=friend_request.status
    )


async def list_friends(
    session: AsyncSession,
    member_id: uuid.UUID,
    *,
    page: int = 1,
    nickname: str | None = None,
    user_number: str | None = None,
) -> FriendListResponse:
    """FR-034: substring filter on nickname/user_number, applied in Python
    after loading all accepted relationships — mirrors
    `build_member_match_records`'s existing precedent (plan.md Scale/Scope:
    a single member's friend count is small enough that this is cheap)."""
    result = await session.execute(
        select(FriendRequest).where(
            FriendRequest.status == "accepted",
            or_(FriendRequest.requester_id == member_id, FriendRequest.addressee_id == member_id),
        )
    )
    requests = list(result.scalars())
    other_id_to_request_id = {
        (fr.addressee_id if fr.requester_id == member_id else fr.requester_id): fr.id
        for fr in requests
    }
    other_ids = list(other_id_to_request_id)
    if not other_ids:
        return FriendListResponse(friends=[], page=page, total_pages=1)

    members_result = await session.execute(select(Member).where(Member.id.in_(other_ids)))
    members_by_id = {m.id: m for m in members_result.scalars()}

    friends: list[FriendSummary] = []
    for other_id in other_ids:
        member = members_by_id.get(other_id)
        if member is None:
            continue
        if nickname and (
            member.nickname is None or nickname.lower() not in member.nickname.lower()
        ):
            continue
        if user_number and user_number.lower() not in member.user_number.lower():
            continue
        friends.append(
            FriendSummary(
                member_id=str(member.id),
                nickname=member.nickname,
                user_number=member.user_number,
                friend_request_id=str(other_id_to_request_id[other_id]),
            )
        )

    friends.sort(key=lambda f: f.user_number)
    total = len(friends)
    total_pages = max(1, (total + _FRIEND_LIST_PAGE_SIZE - 1) // _FRIEND_LIST_PAGE_SIZE)
    start = (page - 1) * _FRIEND_LIST_PAGE_SIZE
    page_friends = friends[start : start + _FRIEND_LIST_PAGE_SIZE]
    return FriendListResponse(friends=page_friends, page=page, total_pages=total_pages)


async def list_incoming_requests(
    session: AsyncSession, member_id: uuid.UUID
) -> IncomingFriendRequestsResponse:
    result = await session.execute(
        select(FriendRequest)
        .where(FriendRequest.addressee_id == member_id, FriendRequest.status == "pending")
        .order_by(FriendRequest.created_at.desc())
    )
    requests = list(result.scalars())
    if not requests:
        return IncomingFriendRequestsResponse(requests=[])

    requester_ids = [fr.requester_id for fr in requests]
    members_result = await session.execute(select(Member).where(Member.id.in_(requester_ids)))
    members_by_id = {m.id: m for m in members_result.scalars()}

    items: list[IncomingFriendRequest] = []
    for fr in requests:
        requester = members_by_id.get(fr.requester_id)
        if requester is None:
            continue
        items.append(
            IncomingFriendRequest(
                friend_request_id=str(fr.id),
                requester=FriendSummary(
                    member_id=str(requester.id),
                    nickname=requester.nickname,
                    user_number=requester.user_number,
                ),
                created_at=fr.created_at.isoformat(),
            )
        )
    return IncomingFriendRequestsResponse(requests=items)


async def respond_friend_request(
    session: AsyncSession, member_id: uuid.UUID, friend_request_id: uuid.UUID, *, accept: bool
) -> FriendRequestResponse:
    """Errors: `FRIEND_REQUEST_NOT_FOUND` (includes "not the addressee",
    avoiding leaking whether the request exists at all), `FRIEND_REQUEST_NOT_PENDING`."""
    result = await session.execute(
        select(FriendRequest).where(FriendRequest.id == friend_request_id)
    )
    friend_request = result.scalar_one_or_none()
    if friend_request is None or friend_request.addressee_id != member_id:
        raise ApiError("FRIEND_REQUEST_NOT_FOUND", status_code=404)
    if friend_request.status != "pending":
        raise ApiError("FRIEND_REQUEST_NOT_PENDING", status_code=409)

    friend_request.status = "accepted" if accept else "rejected"
    friend_request.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(friend_request)
    return FriendRequestResponse(
        friend_request_id=str(friend_request.id), status=friend_request.status
    )


async def unfriend(
    session: AsyncSession, member_id: uuid.UUID, friend_request_id: uuid.UUID
) -> FriendRequestResponse:
    """FR-043~046: `accepted -> unfriended`. Deliberately does not publish
    any Ably event or send any notification — the other member only learns
    of this the next time they load their own `GET /friends` (FR-045)."""
    result = await session.execute(
        select(FriendRequest).where(FriendRequest.id == friend_request_id)
    )
    friend_request = result.scalar_one_or_none()
    if friend_request is None or member_id not in (
        friend_request.requester_id,
        friend_request.addressee_id,
    ):
        raise ApiError("FRIEND_REQUEST_NOT_FOUND", status_code=404)
    if friend_request.status != "accepted":
        raise ApiError("FRIEND_REQUEST_NOT_ACCEPTED", status_code=409)

    friend_request.status = "unfriended"
    friend_request.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(friend_request)
    return FriendRequestResponse(
        friend_request_id=str(friend_request.id), status=friend_request.status
    )
