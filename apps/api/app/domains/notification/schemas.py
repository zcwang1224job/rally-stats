"""Pydantic request/response schemas for the notification domain, per
specs/012-realtime-notifications/contracts/notification-api.md."""

from typing import Literal

from pydantic import BaseModel

from app.domains.friend.schemas import FriendRequestStatus, FriendSummary

NotificationType = Literal["friend_request"]


class FriendRequestNotificationDetail(BaseModel):
    friend_request_id: str
    status: FriendRequestStatus
    requester: FriendSummary


class NotificationSummary(BaseModel):
    notification_id: str
    type: NotificationType
    read: bool
    created_at: str
    # Populated when type == "friend_request" (today, always). A future
    # notification type adds its own nullable field alongside this one
    # rather than replacing it (data-model.md).
    friend_request: FriendRequestNotificationDetail | None = None


class NotificationListResponse(BaseModel):
    notifications: list[NotificationSummary]
    unread_count: int
    page: int
    total_pages: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkNotificationReadResponse(BaseModel):
    notification_id: str
    read: bool


class MarkAllReadResponse(BaseModel):
    marked_count: int
