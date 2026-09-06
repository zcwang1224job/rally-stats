// Mirrors apps/api/app/domains/friend/schemas.py and the relevant shapes in
// apps/api/app/domains/member/schemas.py — see
// specs/006-member-friends/contracts/{friends-api,member-api}.md.

export type FriendshipStatus = 'none' | 'pending_outgoing' | 'pending_incoming' | 'friends';

export interface SearchMemberResponse {
  member_id: string;
  nickname: string | null;
  user_number: string;
  friendship_status: FriendshipStatus;
}

export interface FriendSummary {
  member_id: string;
  nickname: string | null;
  user_number: string;
  /** Populated by `GET /friends` (needed for the unfriend action); left
   * `null` when this shape is nested inside `IncomingFriendRequest`, whose
   * own top-level `friend_request_id` already covers that case. */
  friend_request_id: string | null;
}

export interface FriendListResponse {
  friends: FriendSummary[];
  page: number;
  total_pages: number;
}

export interface FriendRequestResponse {
  friend_request_id: string;
  status: 'pending' | 'accepted' | 'rejected' | 'unfriended';
}

export interface IncomingFriendRequest {
  friend_request_id: string;
  requester: FriendSummary;
  created_at: string;
}

export interface IncomingFriendRequestsResponse {
  requests: IncomingFriendRequest[];
}

export interface MyGroupSummary {
  group_id: string;
  group_number: number;
  name: string;
  status: 'active' | 'disbanded';
}

export interface MyGroupsResponse {
  groups: MyGroupSummary[];
}

export interface ForgotAdminPinResponse {
  admin_pin: string;
  admin_token: string;
}
