"""Pydantic request/response schemas for the friend domain, per
specs/006-member-friends/contracts/friends-api.md."""

from pydantic import BaseModel

FriendRequestStatus = str  # "pending" | "accepted" | "rejected" | "unfriended"


class FriendSummary(BaseModel):
    member_id: str
    nickname: str | None
    user_number: str
    # 010-app-wide-ui-redesign: the original 006 contract's `GET /friends`
    # response shape omitted this, but the frontend's unfriend action
    # (`DELETE /friends/{friend_request_id}`) needs it to know which row to
    # target — populated in `list_friends()`, left `None` when this schema
    # is reused inside `IncomingFriendRequest` (whose own top-level
    # `friend_request_id` field already covers that case).
    friend_request_id: str | None = None


class FriendListResponse(BaseModel):
    friends: list[FriendSummary]
    page: int
    total_pages: int


class FriendRequestCreate(BaseModel):
    addressee_user_number: str


class FriendRequestResponse(BaseModel):
    friend_request_id: str
    status: FriendRequestStatus


class IncomingFriendRequest(BaseModel):
    friend_request_id: str
    requester: FriendSummary
    created_at: str


class IncomingFriendRequestsResponse(BaseModel):
    requests: list[IncomingFriendRequest]
