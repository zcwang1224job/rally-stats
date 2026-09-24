// Mirrors apps/api/app/domains/group/schemas.py's join-flow additions — see
// specs/004-join-group/contracts/group-list-api.md, join-api.md.

import { MatchMode, SchedulingMechanism } from '../../features/group-admin/group-admin.models';
import { SportSummary } from './sport.models';

export interface GroupListItem {
  group_id: string;
  group_number: number;
  name: string;
  has_password: boolean;
  current_member_count: number;
  max_members: number;
  match_mode: MatchMode;
  scheduling_mechanism: SchedulingMechanism;
  activity_time_start: string | null;
  activity_time_end: string | null;
  status: 'active' | 'disbanded';
  court_names: string[];
  creator_nickname: string;
  joined_by_me: boolean | null;
  // True only when the logged-in Member created this group — a subset of
  // joined_by_me, lets "回到我的團" route the creator to the admin page.
  created_by_me?: boolean | null;
  // True when the logged-in Member has an active RosterEntry in a
  // DIFFERENT group — never true alongside joined_by_me for the same item.
  // Lets the list disable "加入" for every other group up front instead of
  // only failing after the Member picks one and confirms (the backend
  // still enforces this regardless — ALREADY_ACTIVE_IN_ANOTHER_GROUP).
  member_active_elsewhere?: boolean | null;
  /** 043 US6: the group's activity (optional for an older backend). */
  sport?: SportSummary;
}

export interface GroupListResponse {
  groups: GroupListItem[];
  page: number;
  total_pages: number;
}

export interface JoinLinkPreviewResponse extends Omit<GroupListItem, 'joined_by_me'> {
  already_joined: boolean;
  roster_entry_id: string | null;
}

export interface VerifyPasswordResponse {
  correct: boolean;
}

export interface JoinGroupRequest {
  password?: string | null;
  nickname?: string | null;
}

export interface JoinGroupResponse {
  roster_entry_id: string;
  nickname: string;
  guest_session_token: string | null;
  created_new: boolean;
}

export interface GuestSessionResponse {
  roster_entry_id: string;
  group_id: string;
  nickname: string;
}

// --- 028-guest-stats-binding ---

export interface BindingStatusResponse {
  already_bound: boolean;
  roster_entry_id: string;
  group_id: string;
  group_name: string;
  nickname: string;
  group_status: 'active' | 'disbanded';
  roster_status: 'active' | 'left' | 'kicked';
  /** The logged-in caller (if any) already has an active roster entry in
   * this group, so `POST .../bind` would refuse them with
   * `MEMBER_ALREADY_IN_GROUP` — the binding entry point is left out
   * entirely rather than offered and then failed. Always false for an
   * anonymous request, which is the normal 訪客 case. */
  already_in_group: boolean;
}

export interface BindRequest {
  mode?: 'register' | 'login' | null;
  email?: string | null;
  password?: string | null;
  turnstile_token?: string | null;
}

export interface BindResponse {
  bound: boolean;
  group_id: string;
  access_token: string | null;
  refresh_token: string | null;
}
