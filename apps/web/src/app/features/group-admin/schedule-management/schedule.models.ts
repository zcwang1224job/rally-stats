// Mirrors apps/api/app/domains/schedule/schemas.py — see contracts/schedule-api.md.

import type { ServeStationInfo } from '../../../core/api/court-live-state.models';

export type Team = 'A' | 'B';
export type WaitingReason = 'manual_assignment' | 'no_queued_match';
// 018-plan-then-start: null for scheduling_mechanism === 'manual', which has
// no plan/start split.
export type RoundPhase = 'awaiting_plan' | 'awaiting_start' | 'in_progress';

export interface ParticipantSummary {
  roster_entry_id: string;
  nickname: string;
  team: Team;
  /** 026-match-record-friend-invite: populated only on match-record rows
   * (match-history, group-member-view/match-records) — always undefined/
   * null on every schedule/live-status participant (current_match,
   * next_up), where the roster list's own member_id is the "加好友" entry
   * point's source instead (research.md #1's redesign). */
  member_id?: string | null;
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
  // feature/control-panel-scoreboard-style: lets court-control.component show
  // the same serve-rotation stations as the scoreboard/public control panel.
  // null when the match has no serve state yet (a match created before
  // 030-score-serve-record's migration).
  serve: ServeStationInfo | null;
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
  // feature/control-panel-scoreboard-style: lets court-control.component
  // patch its own station display directly from this response instead of
  // waiting on its own match.scoreUpdated realtime echo — null when the
  // match just ended this point (no more serve state to show) or the
  // mutation wasn't applied.
  serve: ServeStationInfo | null;
}

export interface RosterScheduleStatus {
  roster_entry_id: string;
  nickname: string;
  status: string;
  wait_count: number | null;
  currently_playing: boolean;
  is_creator: boolean;
  is_guest: boolean;
  /** 026-match-record-friend-invite: null for Guests — the roster list
   * (member-schedule page and admin roster tab, same backend builder) is
   * the "加好友" entry point's canonical home. */
  member_id?: string | null;
}

export interface ScheduleResponse {
  current_round_number: number;
  scheduling_mechanism: string;
  auto_next_round: boolean;
  round_phase: RoundPhase | null;
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
