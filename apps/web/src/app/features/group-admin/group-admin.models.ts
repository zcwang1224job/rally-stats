// Mirrors apps/api/app/domains/group/schemas.py — see contracts/groups-api.md.

import type { SportSummary } from '../../core/api/sport.models';

export type MatchMode = 'singles' | 'doubles';
export type SchedulingMechanism =
  | 'fair_rotation'
  | 'fixed_partner'
  | 'individual_mixed'
  | 'manual';
export type ScoringMode = '21pt' | '15pt' | 'custom';
// 011-round-robin-scheduling: only meaningful when scheduling_mechanism ===
// 'fixed_partner' — see PartnershipSettingsComponent.
export type PartnerSource = 'manual' | 'auto';

export interface CustomScoring {
  target_score: number;
  deuce_threshold: number;
  cap_score: number;
}

/** 043 contracts/sports-api.md §3: which activity a new group is for. */
export interface SportRef {
  sport_key: string;
  custom_sport_id?: string;
  name?: string;
}

export interface CreateGroupRequest {
  name: string;
  password?: string | null;
  max_members: number;
  match_mode: MatchMode;
  scheduling_mechanism: SchedulingMechanism;
  scoring_mode: ScoringMode;
  custom_scoring?: CustomScoring | null;
  activity_time_start?: string | null;
  activity_time_end?: string | null;
  creator_nickname?: string | null;
  turnstile_token: string;
  // 043: the activity and its common parameters (left out = its defaults).
  sport?: SportRef;
  team_size?: number;
  end_mode?: 'target' | 'manual';
  target_score?: number;
  win_by?: number;
  cap_score?: number | null;
  allow_draw?: boolean;
  score_steps?: number[];
  type_params?: Record<string, unknown>;
}

export interface CreateGroupResponse {
  group_id: string;
  group_number: number;
  admin_pin: string;
  admin_token: string;
  current_member_count: number;
  roster_entry_id: string;
  guest_session_token: string | null;
}

export interface GroupPublic {
  group_id: string;
  group_number: number;
  name: string;
  has_password: boolean;
  current_member_count: number;
  max_members: number;
  match_mode: MatchMode;
  scheduling_mechanism: SchedulingMechanism;
  partner_source: PartnerSource;
  activity_time_start: string | null;
  activity_time_end: string | null;
  status: 'active' | 'disbanded';
  // Only set by GET /groups/{group_id} when called with a logged-in
  // Member's Bearer token — null for Guests/unauthenticated callers.
  already_joined?: boolean | null;
  // 013-group-invite-friends: true only for a group created by a logged-in
  // Member — gates whether the admin page's "邀請好友" section is offered.
  created_by_member: boolean;
  /** 043: the group's activity and players per team (optional so an older
   * backend reads as badminton). */
  sport?: SportSummary;
  team_size?: number;
}

export interface ReauthResponse {
  admin_token: string;
  group_id: string;
}

export interface AdminGroupResponse {
  group: GroupPublic;
  password_plaintext: string | null;
  read_only: boolean;
  base_settings_version: number;
  admin_token_version: number;
  join_link_token: string;
  join_link_version: number;
  all_courts_control_panel_token: string;
  all_courts_link_version: number;
  // 018-plan-then-start follow-up: admin-only, deliberately not part of
  // GroupPublic (that also backs the public join-flow lookup).
  scoreboard_scoring_enabled: boolean;
  // 031-shot-placement-scoring: same admin-only rationale as above.
  detailed_scoring_enabled: boolean;
  // 目前生效的分數制度 —— 管理頁的「比賽設定」據此還原團真正的設定，
  // 而不是停在表單寫死的預設值。非 custom 模式時，三個數值即是該預設的
  // 展開值（後端 service._SCORING_PRESETS）。
  scoring_mode: ScoringMode;
  target_score: number;
  deuce_threshold: number;
  /** 043: null = no cap. */
  cap_score: number | null;
  // 043: the rest of the common parameters, and the named presets this
  // activity offers ([] = edit the numbers). Optional for older backends.
  end_mode?: 'target' | 'manual';
  win_by?: number;
  allow_draw?: boolean;
  score_steps?: number[];
  type_params?: Record<string, unknown>;
  scoring_presets?: string[];
}

export interface EditGroupRequest {
  expected_version: number;
  name?: string;
  password?: string | null;
  match_mode?: MatchMode;
  scheduling_mechanism?: SchedulingMechanism;
  partner_source?: PartnerSource;
  max_members?: number;
  activity_time_start?: string | null;
  activity_time_end?: string | null;
}

export interface EditScoringSettingsRequest {
  expected_version: number;
  scoring_mode: ScoringMode;
  target_score?: number;
  deuce_threshold?: number;
  /** 043: null (sent explicitly) = no cap. */
  cap_score?: number | null;
  end_mode?: 'target' | 'manual';
  win_by?: number;
  allow_draw?: boolean;
  score_steps?: number[];
  type_params?: Record<string, unknown>;
}

export interface RegeneratePinResponse {
  admin_pin: string;
  admin_token: string;
}

export interface RegenerateJoinLinkResponse {
  join_link_token: string;
  join_link_version: number;
}

export interface RegenerateAllCourtsLinkResponse {
  all_courts_control_panel_token: string;
  all_courts_link_version: number;
}

export interface ScoreboardScoringResponse {
  scoreboard_scoring_enabled: boolean;
}

export interface DetailedScoringResponse {
  detailed_scoring_enabled: boolean;
}
