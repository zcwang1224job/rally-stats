"""Notification domain REST endpoints, per
specs/012-realtime-notifications/contracts/notification-api.md."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domains.member.models import Member
from app.domains.member.security import require_verified_member
from app.domains.notification import service
from app.domains.notification.schemas import (
    MarkAllReadResponse,
    MarkNotificationReadResponse,
    NotificationListResponse,
    UnreadCountResponse,
)

router = APIRouter(tags=["notification"])


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
) -> NotificationListResponse:
    """FR-004/005: newest-first, read/unread per row."""
    return await service.list_notifications(session, member.id, page)


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UnreadCountResponse:
    """FR-006: lightweight endpoint for the nav-shell badge — called on
    every main page load plus on `notification.created`/reconnect."""
    return await service.get_unread_count(session, member.id)


@router.post("/notifications/{notification_id}/read", response_model=MarkNotificationReadResponse)
async def mark_notification_read(
    notification_id: uuid.UUID,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MarkNotificationReadResponse:
    """FR-007: idempotent. Errors: `NOTIFICATION_NOT_FOUND` (also covers
    "not this member's notification")."""
    notification = await service.mark_notification_read(session, member.id, notification_id)
    return MarkNotificationReadResponse(
        notification_id=str(notification.id), read=notification.read_at is not None
    )


@router.post("/notifications/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MarkAllReadResponse:
    """FR-008."""
    return await service.mark_all_read(session, member.id)
