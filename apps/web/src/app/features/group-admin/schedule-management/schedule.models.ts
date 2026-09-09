// Mirrors apps/api/app/domains/schedule/schemas.py — see contracts/schedule-api.md.

export type Team = 'A' | 'B';
export type WaitingReason = 'manual_assignment' | 'no_queued_match';

export interface ParticipantSummary {
  roster_entry_id: string;
  nickname: string;
  team: Team;
}

export interface NextUpPreview {
  match_id: string;
  participants: ParticipantSummary[];
}

export interface MatchSummary {
  match_id: string;
  status: string;
  participants: ParticipantSummary[];
  score_a: number;
  score_b: number;
}

export interface CourtScheduleStatus {
  court_id: string;
  name: string;
  current_match: MatchSummary | null;
  waiting_reason: WaitingReason | null;
  next_up: NextUpPreview | null;
}

export interface ScoreMutationResult {
  applied: boolean;
  match_id: string;
  status: string;
  score_a: number;
  score_b: number;
  winner_team: Team | null;
}

export interface RosterScheduleStatus {
  roster_entry_id: string;
  nickname: string;
  status: string;
  wait_count: number | null;
  currently_playing: boolean;
  is_creator: boolean;
  is_guest: boolean;
}

export interface ScheduleResponse {
  current_round_number: number;
  scheduling_mechanism: string;
  auto_next_round: boolean;
  courts: CourtScheduleStatus[];
  roster: RosterScheduleStatus[];
}

export interface MatchDetailResponse {
  match_id: string;
  status: string;
  participants: ParticipantSummary[];
  target_score: number;
  deuce_threshold: number;
  cap_score: number;
}

export interface RosterSummary {
  roster_entry_id: string;
  nickname: string;
}

export interface PartnershipSummary {
  partnership_id: string;
  player_a: RosterSummary;
  player_b: RosterSummary;
}

export interface PartnershipsResponse {
  partnerships: PartnershipSummary[];
  unpaired: RosterSummary[];
}

export interface KickMemberResponse {
  roster_entry_id: string;
  status: string;
}

export interface RegenerateGuestLinkResponse {
  roster_entry_id: string;
  guest_session_token: string;
}

// 011-round-robin-scheduling: 本輪賽程清單 — 涵蓋 queued/in_progress/
// completed/abandoned 全部狀態，不像 CourtScheduleStatus.current_match
// 只顯示場地目前這一場。
export interface RoundMatchSummary {
  match_id: string;
  status: string;
  court_name: string | null;
  participants: ParticipantSummary[];
  score_a: number;
  score_b: number;
  winner_team: Team | null;
}

export interface RoundMatchesResponse {
  round_number: number;
  matches: RoundMatchSummary[];
}

// 017-fixed-partner-autofill: 暫時隨機配對——刻意沒有 partnership_id，
// 因為它從來不是一筆寫入資料庫的資料（data-model.md）。
export interface TemporaryPairing {
  player_a: RosterSummary;
  player_b: RosterSummary;
}

export interface TemporaryPairingsResponse {
  pairings: TemporaryPairing[];
}
