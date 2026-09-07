"""Pydantic request/response schemas for the group_invite domain, per
specs/013-group-invite-friends/contracts/group-invite-api.md and
data-model.md."""

from typing import Literal

from pydantic import BaseModel

GroupInviteStatus = Literal["pending", "accepted", "declined", "invalidated"]
InviteStatusForFriend = Literal[
    "not_invited", "pending", "accepted", "declined", "invalidated", "already_member"
]


class InvitableFriendSummary(BaseModel):
    member_id: str
    nickname: str | None
    user_number: str
    invite_status: InviteStatusForFriend
    invite_id: str | None = None


class InvitableFriendsResponse(BaseModel):
    friends: list[InvitableFriendSummary]


class SendGroupInviteRequest(BaseModel):
    invitee_member_id: str


class SendGroupInviteResponse(BaseModel):
    invite_id: str
    status: GroupInviteStatus


class GroupInviteDetailResponse(BaseModel):
    invite_id: str
    status: GroupInviteStatus
    group_id: str
    group_name: str
    inviter_nickname: str | None


class AcceptGroupInviteResponse(BaseModel):
    group_id: str
    roster_entry_id: str
    nickname: str


class DeclineGroupInviteResponse(BaseModel):
    invite_id: str
    status: Literal["declined"]
