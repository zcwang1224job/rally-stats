"""Group-invite domain REST endpoints, per
specs/013-group-invite-friends/contracts/group-invite-api.md.

Two routers, mirroring `group/router.py`'s `router`/`join_router` split:
`router` (creator-facing, under `/groups/{group_id}/...`, `require_admin`)
and `invite_router` (invitee-facing, under `/group-invites/...`,
`require_verified_member`)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import require_admin
from app.domains.group_invite import service
from app.domains.group_invite.schemas import (
    AcceptGroupInviteResponse,
    DeclineGroupInviteResponse,
    GroupInviteDetailResponse,
    InvitableFriendsResponse,
    SendGroupInviteRequest,
    SendGroupInviteResponse,
)
from app.domains.member.models import Member
from app.domains.member.security import require_verified_member

router = APIRouter(prefix="/groups", tags=["group_invite"])
invite_router = APIRouter(prefix="/group-invites", tags=["group_invite"])


@router.get("/{group_id}/invitable-friends", response_model=InvitableFriendsResponse)
async def list_invitable_friends(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InvitableFriendsResponse:
    """Errors: `ADMIN_TOKEN_INVALID`, `GROUP_NOT_MEMBER_CREATED`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    return await service.list_invitable_friends(session, group)


@router.post("/{group_id}/invites", response_model=SendGroupInviteResponse, status_code=201)
async def send_invite(
    group_id: uuid.UUID,
    payload: SendGroupInviteRequest,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SendGroupInviteResponse:
    """Errors: `ADMIN_TOKEN_INVALID`, `GROUP_NOT_MEMBER_CREATED`,
    `MEMBER_NOT_FOUND`, `NOT_FRIENDS`, `ALREADY_GROUP_MEMBER`,
    `INVITE_ALREADY_PENDING`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    if group.created_by_member_id is None:
        raise ApiError("GROUP_NOT_MEMBER_CREATED", status_code=403)
    return await service.send_invite(
        session, group, group.created_by_member_id, uuid.UUID(payload.invitee_member_id)
    )


@invite_router.get("/{invite_id}", response_model=GroupInviteDetailResponse)
async def get_invite_detail(
    invite_id: uuid.UUID,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GroupInviteDetailResponse:
    """Errors: `GROUP_INVITE_NOT_FOUND`."""
    return await service.get_invite_detail(session, member.id, invite_id)


@invite_router.post("/{invite_id}/accept", response_model=AcceptGroupInviteResponse)
async def accept_invite(
    invite_id: uuid.UUID,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AcceptGroupInviteResponse:
    """Errors: `GROUP_INVITE_NOT_FOUND`, `GROUP_INVITE_NOT_PENDING`,
    `GROUP_DISBANDED`, `GROUP_FULL`, `ALREADY_ACTIVE_IN_ANOTHER_GROUP`,
    `MEMBER_NICKNAME_NOT_SET`."""
    return await service.accept_invite(session, member, invite_id)


@invite_router.post("/{invite_id}/decline", response_model=DeclineGroupInviteResponse)
async def decline_invite(
    invite_id: uuid.UUID,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeclineGroupInviteResponse:
    """Errors: `GROUP_INVITE_NOT_FOUND`, `GROUP_INVITE_NOT_PENDING`."""
    return await service.decline_invite(session, member.id, invite_id)
