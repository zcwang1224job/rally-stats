"""Group-invite domain service layer, per
specs/013-group-invite-friends/plan.md.

Reads from `group.service`/`friend.service` (never modifies their core
logic) and calls into `notification.service` to deliver both new
notification types — but is never imported BACK by either `group.service`
or `friend.service` themselves (research.md #1): the optional
`invalidate_pending_invites*` hooks used by `disband_group()`/`unfriend()`
are wired at the router/scheduler layer only (research.md #2), the same
`AbandonMatchesHook` pattern 003 established, so no cross-module import
cycle is ever formed.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.friend.models import FriendRequest
from app.domains.friend.service import get_friendship_status
from app.domains.group.models import Group
from app.domains.group.service import get_group_by_id, join_group
from app.domains.group_invite.models import GroupInvite
from app.domains.group_invite.schemas import (
    AcceptGroupInviteResponse,
    DeclineGroupInviteResponse,
    GroupInviteDetailResponse,
    InvitableFriendsResponse,
    InvitableFriendSummary,
    InviteStatusForFriend,
    SendGroupInviteResponse,
)
from app.domains.member.models import Member
from app.domains.notification.service import (
    create_group_invite_capacity_full_notification,
    create_group_invite_notification,
    publish_notification_created,
)
from app.domains.roster.models import RosterEntry


async def _get_invite_for_invitee(
    session: AsyncSession, member_id: uuid.UUID, invite_id: uuid.UUID
) -> GroupInvite:
    """Errors: `GROUP_INVITE_NOT_FOUND` (also covers "not this member's
    invite", to avoid revealing whether it exists at all — same convention
    as `respond_friend_request`/`mark_notification_read`)."""
    result = await session.execute(select(GroupInvite).where(GroupInvite.id == invite_id))
    invite = result.scalar_one_or_none()
    if invite is None or invite.invitee_member_id != member_id:
        raise ApiError("GROUP_INVITE_NOT_FOUND", status_code=404)
    return invite


async def send_invite(
    session: AsyncSession,
    group: Group,
    inviter_member_id: uuid.UUID,
    invitee_member_id: uuid.UUID,
) -> SendGroupInviteResponse:
    """FR-001~004. Errors: `GROUP_NOT_MEMBER_CREATED`, `MEMBER_NOT_FOUND`,
    `NOT_FRIENDS`, `ALREADY_GROUP_MEMBER`, `INVITE_ALREADY_PENDING` (pre-check
    plus the partial unique index as the final race-condition guarantee, same
    combined approach as `friend.service.create_friend_request`)."""
    if group.created_by_member_id is None:
        raise ApiError("GROUP_NOT_MEMBER_CREATED", status_code=403)

    invitee_result = await session.execute(select(Member).where(Member.id == invitee_member_id))
    invitee = invitee_result.scalar_one_or_none()
    if invitee is None:
        raise ApiError("MEMBER_NOT_FOUND", status_code=404)

    status = await get_friendship_status(session, inviter_member_id, invitee_member_id)
    if status != "friends":
        raise ApiError("NOT_FRIENDS", status_code=400)

    already_member_result = await session.execute(
        select(RosterEntry.id).where(
            RosterEntry.group_id == group.id,
            RosterEntry.member_id == invitee_member_id,
            RosterEntry.status == "active",
        )
    )
    if already_member_result.scalar_one_or_none() is not None:
        raise ApiError("ALREADY_GROUP_MEMBER", status_code=409)

    pending_result = await session.execute(
        select(GroupInvite.id).where(
            GroupInvite.group_id == group.id,
            GroupInvite.invitee_member_id == invitee_member_id,
            GroupInvite.status == "pending",
        )
    )
    if pending_result.scalar_one_or_none() is not None:
        raise ApiError("INVITE_ALREADY_PENDING", status_code=409)

    invite = GroupInvite(
        group_id=group.id,
        inviter_member_id=inviter_member_id,
        invitee_member_id=invitee_member_id,
        status="pending",
    )
    session.add(invite)
    try:
        await session.flush()
        notification = create_group_invite_notification(invite)
        session.add(notification)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ApiError("INVITE_ALREADY_PENDING", status_code=409) from None
    await session.refresh(invite)
    await publish_notification_created(notification)
    return SendGroupInviteResponse(invite_id=str(invite.id), status=invite.status)


async def list_invitable_friends(session: AsyncSession, group: Group) -> InvitableFriendsResponse:
    """FR-001/004, FR-009 (research.md #8): the creator's full friend list,
    each annotated with `invite_status` — `already_member` is computed LIVE
    against the current roster and always takes priority over a stale
    `GroupInvite` row; otherwise the friend's most recent `GroupInvite` row
    for this group (if any) determines the status. Serves both US1 (pick
    who to invite) and US3 (view status) in one call.

    A friend whose most recent invite is `accepted` but who is no longer an
    active roster member (they left, or were kicked, after accepting) is
    reported as `not_invited` rather than the stale `accepted` — that
    invite's purpose is fulfilled and gone, and leaving it as a permanent
    terminal `accepted` status would strand the creator with no way to
    invite them again (bug report: 團長邀請好友後，對方接受後又退出，這樣
    組團仍然顯示已接受，無法再次邀請). The underlying `GroupInvite` row
    itself is left untouched — this is a read-time presentation decision,
    not a state transition (FR-014's `invalidated` state stays reserved
    for friendship-dissolution/group-disband).

    Errors: `GROUP_NOT_MEMBER_CREATED`."""
    if group.created_by_member_id is None:
        raise ApiError("GROUP_NOT_MEMBER_CREATED", status_code=403)
    inviter_id = group.created_by_member_id

    friend_requests_result = await session.execute(
        select(FriendRequest).where(
            FriendRequest.status == "accepted",
            or_(
                FriendRequest.requester_id == inviter_id,
                FriendRequest.addressee_id == inviter_id,
            ),
        )
    )
    requests = list(friend_requests_result.scalars())
    friend_ids = [
        (fr.addressee_id if fr.requester_id == inviter_id else fr.requester_id) for fr in requests
    ]
    if not friend_ids:
        return InvitableFriendsResponse(friends=[])

    members_result = await session.execute(select(Member).where(Member.id.in_(friend_ids)))
    members_by_id = {m.id: m for m in members_result.scalars()}

    active_roster_result = await session.execute(
        select(RosterEntry.member_id).where(
            RosterEntry.group_id == group.id,
            RosterEntry.member_id.in_(friend_ids),
            RosterEntry.status == "active",
        )
    )
    active_member_ids = {row[0] for row in active_roster_result.all()}

    invites_result = await session.execute(
        select(GroupInvite)
        .where(GroupInvite.group_id == group.id, GroupInvite.invitee_member_id.in_(friend_ids))
        .order_by(GroupInvite.created_at.desc())
    )
    latest_invite_by_friend: dict[uuid.UUID, GroupInvite] = {}
    for invite in invites_result.scalars():
        # First row seen per friend wins — query is already newest-first.
        latest_invite_by_friend.setdefault(invite.invitee_member_id, invite)

    summaries: list[InvitableFriendSummary] = []
    for friend_id in friend_ids:
        member = members_by_id.get(friend_id)
        if member is None:
            continue
        latest = latest_invite_by_friend.get(friend_id)
        invite_status: InviteStatusForFriend
        invite_id: str | None
        if friend_id in active_member_ids:
            invite_status = "already_member"
            invite_id = str(latest.id) if latest is not None else None
        elif latest is None or latest.status == "accepted":
            # `latest is None` → never invited. `latest.status == "accepted"`
            # here specifically means "accepted, but not currently active" —
            # the active case was already handled by the branch above.
            invite_status = "not_invited"
            invite_id = None
        else:
            invite_status = latest.status  # type: ignore[assignment]
            invite_id = str(latest.id)
        summaries.append(
            InvitableFriendSummary(
                member_id=str(friend_id),
                nickname=member.nickname,
                user_number=member.user_number,
                invite_status=invite_status,
                invite_id=invite_id,
            )
        )

    summaries.sort(key=lambda f: f.user_number)
    return InvitableFriendsResponse(friends=summaries)


async def get_invite_detail(
    session: AsyncSession, member_id: uuid.UUID, invite_id: uuid.UUID
) -> GroupInviteDetailResponse:
    """Errors: `GROUP_INVITE_NOT_FOUND`."""
    invite = await _get_invite_for_invitee(session, member_id, invite_id)
    group = await get_group_by_id(session, invite.group_id)
    inviter_result = await session.execute(
        select(Member).where(Member.id == invite.inviter_member_id)
    )
    inviter = inviter_result.scalar_one_or_none()
    return GroupInviteDetailResponse(
        invite_id=str(invite.id),
        status=invite.status,
        group_id=str(invite.group_id),
        group_name=group.name,
        inviter_nickname=inviter.nickname if inviter is not None else None,
    )


async def _notify_inviter_capacity_full(session: AsyncSession, invite: GroupInvite) -> None:
    """FR-013(b): notifies the inviter that this accept attempt failed
    because the group is full. Deliberately does NOT touch `invite.status`
    (FR-013(a) — the invite stays `pending`). Deduped at the DB level
    (`uq_notifications_type_source_member`) across repeat failed attempts
    on the same invite — a duplicate is treated as a silent no-op, not an
    error, so a good-faith retry by the invitee never breaks."""
    notification = create_group_invite_capacity_full_notification(invite)
    session.add(notification)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return
    await session.refresh(notification)
    await publish_notification_created(notification)


async def accept_invite(
    session: AsyncSession, member: Member, invite_id: uuid.UUID
) -> AcceptGroupInviteResponse:
    """FR-006/007/013. Reuses `join_group(skip_password=True)` as the sole
    write path for the actual join (research.md #3) — capacity/disbanded/
    one-active-group-per-member enforcement all stay single-sourced there.
    Errors: `GROUP_INVITE_NOT_FOUND`, `GROUP_INVITE_NOT_PENDING`,
    `GROUP_DISBANDED` (defensive only — disbanding already invalidates
    pending invites via the hook, so `GROUP_INVITE_NOT_PENDING` fires
    first in practice), `GROUP_FULL` (triggers the FR-013 creator
    notification, invite stays pending), `ALREADY_ACTIVE_IN_ANOTHER_GROUP`,
    `MEMBER_NICKNAME_NOT_SET`."""
    invite = await _get_invite_for_invitee(session, member.id, invite_id)
    if invite.status != "pending":
        raise ApiError("GROUP_INVITE_NOT_PENDING", status_code=409)

    group = await get_group_by_id(session, invite.group_id)
    try:
        roster_entry, _created_new = await join_group(
            session,
            group,
            member=member,
            password=None,
            nickname=None,
            skip_password=True,
        )
    except ApiError as exc:
        if exc.error_code == "GROUP_FULL":
            await _notify_inviter_capacity_full(session, invite)
        raise

    invite.status = "accepted"
    invite.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(invite)
    return AcceptGroupInviteResponse(
        group_id=str(group.id),
        roster_entry_id=str(roster_entry.id),
        nickname=roster_entry.nickname,
    )


async def decline_invite(
    session: AsyncSession, member_id: uuid.UUID, invite_id: uuid.UUID
) -> DeclineGroupInviteResponse:
    """FR-008: ends the invite without joining; MUST NOT block future
    re-invites (no other write happens here — a fresh `send_invite()` call
    later creates an independent new row). Errors: `GROUP_INVITE_NOT_FOUND`,
    `GROUP_INVITE_NOT_PENDING`."""
    invite = await _get_invite_for_invitee(session, member_id, invite_id)
    if invite.status != "pending":
        raise ApiError("GROUP_INVITE_NOT_PENDING", status_code=409)

    invite.status = "declined"
    invite.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(invite)
    return DeclineGroupInviteResponse(invite_id=str(invite.id), status="declined")


async def invalidate_pending_invites_for_group(session: AsyncSession, group_id: uuid.UUID) -> None:
    """FR-014/Edge Cases (group disbanded): wired as `disband_group()`'s
    optional `invalidate_pending_invites` hook (research.md #2) — called
    from both the manual disband endpoint and the auto-disband sweep, both
    inside the SAME transaction the caller commits, so this deliberately
    does not commit itself."""
    await session.execute(
        update(GroupInvite)
        .where(GroupInvite.group_id == group_id, GroupInvite.status == "pending")
        .values(status="invalidated", updated_at=datetime.now(UTC))
    )


async def invalidate_pending_invites_for_member_pair(
    session: AsyncSession, member_a: uuid.UUID, member_b: uuid.UUID
) -> None:
    """FR-014 (Clarifications Q3): wired as `unfriend()`'s optional
    `invalidate_pending_invites` hook — invites are always one-directional
    (only the creator invites), so this checks both orderings of the pair.
    Same non-committing contract as the group-scoped variant above."""
    await session.execute(
        update(GroupInvite)
        .where(
            GroupInvite.status == "pending",
            or_(
                and_(
                    GroupInvite.inviter_member_id == member_a,
                    GroupInvite.invitee_member_id == member_b,
                ),
                and_(
                    GroupInvite.inviter_member_id == member_b,
                    GroupInvite.invitee_member_id == member_a,
                ),
            ),
        )
        .values(status="invalidated", updated_at=datetime.now(UTC))
    )
