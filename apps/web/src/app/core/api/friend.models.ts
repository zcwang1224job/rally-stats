// Mirrors apps/api/app/domains/friend/schemas.py and the relevant shapes in
// apps/api/app/domains/member/schemas.py — see
// specs/006-member-friends/contracts/{friends-api,member-api}.md and
// specs/014-member-groups-history/contracts/member-groups-history-api.md.

import {
  FinalStandingRow,
  MatchRecordScoreComparison,
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
 * always unfiltered by that same search. `final_standings`
 * (019-group-final-standings) is a third, equally independent section: the
 * group's whole final team ranking, covering every ever-participant.
 * `player_records` (pie-chart addition) moves with `matches`' filters —
 * every player who appeared anywhere in the FULL filtered result set (not
 * just the current page), each with a win/loss tally over that set. */
export interface MemberGroupHistoryResponse {
  group_id: string;
  group_name: string;
  my_stats: MemberGroupStatsResponse;
  final_standings: FinalStandingRow[];
  matches: MatchRecordSummary[];
  page: number;
  total_pages: number;
  player_records: OpponentRecord[];
}

/** Advanced filters for `MemberGroupHistoryResponse.matches`. `nickname`
 * matches any participant on either team. `group1_player1`/
 * `group1_player2` and `group2_player1`/`group2_player2` search for a
 * "this group of people vs. that group of people" matchup — NOT which
 * literal on-court team (A or B) either group happened to land on, which
 * the viewer can't see and shouldn't need to guess; filling both fields
 * for one group requires two DISTINCT players who were on the SAME side
 * together, one per field. `score_a_cmp`+`score_a`/`score_b_cmp`+
 * `score_b`, by contrast, DO stay tied to each match's literal A/B
 * sides — there's no "self"/"opponent" for a plain score comparison,
 * unlike `MemberMatchRecordFilters` (this list has no single "my team").
 * None of this narrows `my_stats`, which always stays this member's full
 * history. */
export interface MemberGroupHistoryFilters {
  nickname?: string;
  round_from?: number;
  round_to?: number;
  group1_player1?: string;
  group1_player2?: string;
  group2_player1?: string;
  group2_player2?: string;
  score_a_cmp?: MatchRecordScoreComparison;
  score_a?: number;
  score_b_cmp?: MatchRecordScoreComparison;
  score_b?: number;
}
