// Mirrors apps/api/app/domains/group/schemas.py's join-flow additions — see
// specs/004-join-group/contracts/group-list-api.md, join-api.md.

import { MatchMode, SchedulingMechanism } from '../../features/group-admin/group-admin.models';

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
