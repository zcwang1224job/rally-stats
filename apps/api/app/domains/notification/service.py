"""Notification domain service layer. Per
specs/012-realtime-notifications/plan.md.

`create_friend_request_notification()` is the only cross-module entry
point — called by `app.domains.friend.service.create_friend_request()`
inside the same DB transaction (research.md #4). Everything else here only
ever touches the calling member's own notifications (FR-009)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.realtime import member_notifications_channel, publish
from app.domains.friend.models import FriendRequest
from app.domains.friend.schemas import FriendSummary
from app.domains.group.models import Group
from app.domains.group_invite.models import GroupInvite
from app.domains.member.models import Member
from app.domains.notification.models import Notification
from app.domains.notification.schemas import (
    FriendRequestNotificationDetail,
    GroupInviteNotificationDetail,
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationSummary,
    UnreadCountResponse,
)
from app.system_config.service import get_default_page_size


def create_friend_request_notification(friend_request: FriendRequest) -> Notification:
    """Only `session.add()`s the row — does NOT commit. The caller
    (`friend/service.py`'s `create_friend_request()`) MUST add this in the
    same transaction as the `FriendRequest` it's created from and commit
    both together, so the two can never exist independently
    (research.md #4)."""
    return Notification(
        member_id=friend_request.addressee_id,
        type="friend_request",
        source_id=friend_request.id,
    )


def create_group_invite_notification(group_invite: GroupInvite) -> Notification:
    """013-group-invite-friends FR-005: delivered to the invitee. Same
    non-committing contract as `create_friend_request_notification` above —
    the caller (`group_invite.service.send_invite()`) MUST add this in the
    same transaction as the `GroupInvite` it's created from."""
    return Notification(
        member_id=group_invite.invitee_member_id,
        type="group_invite",
        source_id=group_invite.id,
    )


def create_group_invite_capacity_full_notification(group_invite: GroupInvite) -> Notification:
    """013-group-invite-friends FR-013: delivered to the inviter when an
    accept attempt fails because the group is full. `source_id` stays the
    SAME `GroupInvite.id` across repeat failed attempts — the DB's
    `uq_notifications_type_source_member` constraint then naturally caps
    this at one notification per invite per inviter rather than spamming on
    every retry; the caller MUST catch the resulting `IntegrityError` on a
    duplicate and treat it as a no-op, not a failure."""
    return Notification(
        member_id=group_invite.inviter_member_id,
        type="group_invite_capacity_full",
        source_id=group_invite.id,
    )


async def publish_notification_created(notification: Notification) -> None:
    """Call only AFTER the triggering transaction has committed
    (constitution X). Payload is deliberately minimal — subscribers always
    re-fetch from `GET /notifications/unread-count` rather than rendering
    from the event itself (research.md #6)."""
    await publish(
        member_notifications_channel(str(notification.member_id)),
        "notification.created",
        {"notification_id": str(notification.id), "type": notification.type},
    )


async def get_unread_count(session: AsyncSession, member_id: uuid.UUID) -> UnreadCountResponse:
    result = await session.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.member_id == member_id, Notification.read_at.is_(None))
    )
    return UnreadCountResponse(unread_count=result.scalar_one())


async def _build_notification_summaries(
    session: AsyncSession, notifications: list[Notification]
) -> list[NotificationSummary]:
    """Always live-queries the referenced `FriendRequest`/`Member` rows —
    deliberately not a snapshot (research.md #5), so a request already
    resolved elsewhere (accepted/rejected/withdrawn) shows its current
    status rather than the "pending" it had when the notification was
    created."""
    if not notifications:
        return []
    friend_request_ids = [n.source_id for n in notifications if n.type == "friend_request"]
    friend_requests_by_id: dict[uuid.UUID, FriendRequest] = {}
    members_by_id: dict[uuid.UUID, Member] = {}
    if friend_request_ids:
        result = await session.execute(
            select(FriendRequest).where(FriendRequest.id.in_(friend_request_ids))
        )
        friend_requests_by_id = {fr.id: fr for fr in result.scalars()}

        requester_ids = {fr.requester_id for fr in friend_requests_by_id.values()}
        members_result = await session.execute(select(Member).where(Member.id.in_(requester_ids)))
        members_by_id = {m.id: m for m in members_result.scalars()}

    # 013-group-invite-friends, research.md #7: "group_invite" and
    # "group_invite_capacity_full" share the same underlying GroupInvite
    # row/detail shape, just rendered for a different recipient.
    group_invite_ids = [
        n.source_id
        for n in notifications
        if n.type in ("group_invite", "group_invite_capacity_full")
    ]
    group_invites_by_id: dict[uuid.UUID, GroupInvite] = {}
    groups_by_id: dict[uuid.UUID, Group] = {}
    if group_invite_ids:
        invites_result = await session.execute(
            select(GroupInvite).where(GroupInvite.id.in_(group_invite_ids))
        )
        group_invites_by_id = {gi.id: gi for gi in invites_result.scalars()}

        invite_group_ids = {gi.group_id for gi in group_invites_by_id.values()}
        groups_result = await session.execute(select(Group).where(Group.id.in_(invite_group_ids)))
        groups_by_id = {g.id: g for g in groups_result.scalars()}

        invite_member_ids = {
            member_id
            for gi in group_invites_by_id.values()
            for member_id in (gi.inviter_member_id, gi.invitee_member_id)
        }
        # requester_ids from the friend_request branch above may overlap —
        # merge into the same members_by_id map rather than re-querying.
        missing_member_ids = invite_member_ids - members_by_id.keys()
        if missing_member_ids:
            extra_members_result = await session.execute(
                select(Member).where(Member.id.in_(missing_member_ids))
            )
            members_by_id.update({m.id: m for m in extra_members_result.scalars()})

    def _friend_summary(member_id: uuid.UUID) -> FriendSummary:
        member = members_by_id.get(member_id)
        return FriendSummary(
            member_id=str(member_id),
            nickname=member.nickname if member else None,
            user_number=member.user_number if member else "",
        )

    summaries: list[NotificationSummary] = []
    for notification in notifications:
        friend_request_detail: FriendRequestNotificationDetail | None = None
        if notification.type == "friend_request":
            friend_request = friend_requests_by_id.get(notification.source_id)
            if friend_request is not None:
                friend_request_detail = FriendRequestNotificationDetail(
                    friend_request_id=str(friend_request.id),
                    status=friend_request.status,
                    requester=_friend_summary(friend_request.requester_id),
                )

        group_invite_detail: GroupInviteNotificationDetail | None = None
        if notification.type in ("group_invite", "group_invite_capacity_full"):
            group_invite = group_invites_by_id.get(notification.source_id)
            if group_invite is not None:
                group = groups_by_id.get(group_invite.group_id)
                group_invite_detail = GroupInviteNotificationDetail(
                    invite_id=str(group_invite.id),
                    group_id=str(group_invite.group_id),
                    group_name=group.name if group else "",
                    status=group_invite.status,
                    inviter=_friend_summary(group_invite.inviter_member_id),
                    invitee=_friend_summary(group_invite.invitee_member_id),
                )

        summaries.append(
            NotificationSummary(
                notification_id=str(notification.id),
                type=notification.type,
                read=notification.read_at is not None,
                created_at=notification.created_at.isoformat(),
                friend_request=friend_request_detail,
                group_invite=group_invite_detail,
            )
        )
    return summaries


async def list_notifications(
    session: AsyncSession, member_id: uuid.UUID, page: int = 1
) -> NotificationListResponse:
    """FR-004/005: newest-first, read/unread per row. Purely a read —
    MUST NOT (and does not) touch `read_at` for any row it returns
    (FR-013)."""
    count_result = await session.execute(
        select(func.count()).select_from(Notification).where(Notification.member_id == member_id)
    )
    total = count_result.scalar_one()
    page_size = await get_default_page_size(session)
    total_pages = max(1, (total + page_size - 1) // page_size)

    result = await session.execute(
        select(Notification)
        .where(Notification.member_id == member_id)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    notifications = list(result.scalars())
    summaries = await _build_notification_summaries(session, notifications)

    unread_count = await get_unread_count(session, member_id)
    return NotificationListResponse(
        notifications=summaries,
        unread_count=unread_count.unread_count,
        page=page,
        total_pages=total_pages,
    )


async def mark_notification_read(
    session: AsyncSession, member_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification:
    """FR-007: idempotent — a notification already read stays read (no
    error). Errors: `NOTIFICATION_NOT_FOUND` (also covers "not this
    member's notification", to avoid revealing whether it exists at all,
    same convention as `respond_friend_request`)."""
    result = await session.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notification = result.scalar_one_or_none()
    if notification is None or notification.member_id != member_id:
        raise ApiError("NOTIFICATION_NOT_FOUND", status_code=404)

    await session.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await session.commit()
    await session.refresh(notification)
    return notification


async def mark_all_read(session: AsyncSession, member_id: uuid.UUID) -> MarkAllReadResponse:
    """FR-008. Single atomic `UPDATE ... WHERE read_at IS NULL` — no-op
    (marked_count=0) when there's nothing unread, not an error."""
    result = await session.execute(
        update(Notification)
        .where(Notification.member_id == member_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await session.commit()
    return MarkAllReadResponse(marked_count=result.rowcount)
