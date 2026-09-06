// Mirrors apps/api/app/domains/group/schemas.py — see contracts/groups-api.md.

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
  cap_score?: number;
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
