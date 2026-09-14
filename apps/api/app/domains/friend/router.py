"""Friend domain REST endpoints, per
specs/006-member-friends/contracts/friends-api.md."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domains.friend import service
from app.domains.friend.schemas import (
    FriendListResponse,
    FriendRequestCreate,
    FriendRequestCreateByMemberId,
    FriendRequestResponse,
    IncomingFriendRequestsResponse,
    InviteCandidatesRequest,
    InviteCandidatesResponse,
)
from app.domains.group_invite.service import invalidate_pending_invites_for_member_pair
from app.domains.member.models import Member
from app.domains.member.security import require_verified_member

router = APIRouter(tags=["friend"])


@router.get("/friends", response_model=FriendListResponse)
async def list_friends(
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    nickname: str | None = None,
    user_number: str | None = None,
) -> FriendListResponse:
    """FR-034: substring filter on nickname/user_number."""
    return await service.list_friends(
        session, member.id, page=page, nickname=nickname, user_number=user_number
    )


@router.post("/friends/requests", response_model=FriendRequestResponse, status_code=201)
async def create_friend_request(
    payload: FriendRequestCreate,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FriendRequestResponse:
    """Errors: `MEMBER_NOT_FOUND`, `CANNOT_FRIEND_SELF`,
    `FRIEND_REQUEST_ALREADY_PENDING`, `ALREADY_FRIENDS`."""
    return await service.create_friend_request(session, member.id, payload.addressee_user_number)


@router.post(
    "/friends/requests/by-member", response_model=FriendRequestResponse, status_code=201
)
async def create_friend_request_by_member(
    payload: FriendRequestCreateByMemberId,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FriendRequestResponse:
    """026-match-record-friend-invite FR-001~005: send a friend request by
    `member_id` (from a match-record/live-status page) instead of
    `user_number`. Errors: `MEMBER_NOT_FOUND`, `CANNOT_FRIEND_SELF`,
    `FRIEND_REQUEST_ALREADY_PENDING`, `ALREADY_FRIENDS`,
    `INVITE_VIA_MATCH_PAGES_NOT_ALLOWED`."""
    return await service.create_friend_request_by_member_id(
        session, member.id, uuid.UUID(payload.addressee_member_id)
    )


@router.post("/friends/invite-candidates", response_model=InviteCandidatesResponse)
async def get_invite_candidates(
    payload: InviteCandidatesRequest,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InviteCandidatesResponse:
    """026-match-record-friend-invite: batched relationship + eligibility
    status for every `member_id` a match-record/live-status page currently
    has visible, per contracts/friend-invite-from-pages-api.md."""
    return await service.get_invite_candidates_status(session, member.id, payload.member_ids)


@router.get("/friends/requests/incoming", response_model=IncomingFriendRequestsResponse)
async def list_incoming_requests(
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncomingFriendRequestsResponse:
    """Only `status='pending'` requests where the caller is the `addressee`."""
    return await service.list_incoming_requests(session, member.id)


@router.post("/friends/requests/{friend_request_id}/accept", response_model=FriendRequestResponse)
async def accept_friend_request(
    friend_request_id: uuid.UUID,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FriendRequestResponse:
    """Errors: `FRIEND_REQUEST_NOT_FOUND`, `FRIEND_REQUEST_NOT_PENDING`."""
    return await service.respond_friend_request(session, member.id, friend_request_id, accept=True)


@router.post("/friends/requests/{friend_request_id}/reject", response_model=FriendRequestResponse)
async def reject_friend_request(
    friend_request_id: uuid.UUID,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FriendRequestResponse:
    """Errors: `FRIEND_REQUEST_NOT_FOUND`, `FRIEND_REQUEST_NOT_PENDING`."""
    return await service.respond_friend_request(session, member.id, friend_request_id, accept=False)


@router.delete("/friends/{friend_request_id}", response_model=FriendRequestResponse)
async def unfriend(
    friend_request_id: uuid.UUID,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FriendRequestResponse:
    """FR-045: MUST NOT notify the other party. Errors:
    `FRIEND_REQUEST_NOT_FOUND`, `FRIEND_REQUEST_NOT_ACCEPTED`."""
    return await service.unfriend(
        session,
        member.id,
        friend_request_id,
        invalidate_pending_invites=invalidate_pending_invites_for_member_pair,
    )
