// Mirrors apps/api/app/domains/friend/schemas.py and the relevant shapes in
// apps/api/app/domains/member/schemas.py — see
// specs/006-member-friends/contracts/{friends-api,member-api}.md and
// specs/014-member-groups-history/contracts/member-groups-history-api.md.

import {
  MatchRecordSummary,
  OpponentRecord,
  RoundWinRatePoint,
} from './group-member-view.models';

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
  created_at: string;
  // null for a still-active group, and for a group disbanded before this
  // field existed (that disband time was never recorded).
  disbanded_at: string | null;
  // 014-member-groups-history: whether this member created the group.
  is_creator: boolean;
  // This member's own most-recent roster status in this group — a member
  // can leave and rejoin the same group, producing multiple historical
  // entries; this reflects the newest one.
  member_status: 'active' | 'left' | 'kicked';
}

export interface MyGroupsResponse {
  groups: MyGroupSummary[];
}

export interface ForgotAdminPinResponse {
  admin_pin: string;
  admin_token: string;
}

/** This member's own performance within one group — always reflects their
 * FULL history there, never narrowed by `MemberGroupHistoryResponse
 * .matches`' own nickname search (which searches the group's shared match
 * list, not "my" games specifically). */
export interface MemberGroupStatsResponse {
  total_matches: number;
  total_wins: number;
  total_losses: number;
  win_rate: number;
  round_win_rates: RoundWinRatePoint[];
  opponent_records: OpponentRecord[];
}

/** `matches` is the group's own shared match history (every completed
 * match, any participant), optionally searched by nickname across either
 * team; `my_stats` is this member's personal performance in the group,
 * always unfiltered by that same search. */
export interface MemberGroupHistoryResponse {
  group_id: string;
  group_name: string;
  my_stats: MemberGroupStatsResponse;
  matches: MatchRecordSummary[];
  page: number;
  total_pages: number;
}
