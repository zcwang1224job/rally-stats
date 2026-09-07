"""Pydantic request/response schemas for the notification domain, per
specs/012-realtime-notifications/contracts/notification-api.md."""

from typing import Literal

from pydantic import BaseModel

from app.domains.friend.schemas import FriendRequestStatus, FriendSummary

NotificationType = Literal["friend_request", "group_invite", "group_invite_capacity_full"]


class FriendRequestNotificationDetail(BaseModel):
    friend_request_id: str
    status: FriendRequestStatus
    requester: FriendSummary


class GroupInviteNotificationDetail(BaseModel):
    """013-group-invite-friends, research.md #7: the same shape backs both
    new `type` values (`"group_invite"` delivered to the invitee,
    `"group_invite_capacity_full"` delivered to the inviter) — same
    underlying `GroupInvite` row, rendered from whichever recipient's
    perspective the notification belongs to."""

    invite_id: str
    group_id: str
    group_name: str
    status: Literal["pending", "accepted", "declined", "invalidated"]
    inviter: FriendSummary
    invitee: FriendSummary


class NotificationSummary(BaseModel):
    notification_id: str
    type: NotificationType
    read: bool
    created_at: str
    # Populated when type == "friend_request". A future notification type
    # adds its own nullable field alongside this one rather than replacing
    # it (data-model.md).
    friend_request: FriendRequestNotificationDetail | None = None
    # Populated when type is "group_invite" or "group_invite_capacity_full".
    group_invite: GroupInviteNotificationDetail | None = None


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
