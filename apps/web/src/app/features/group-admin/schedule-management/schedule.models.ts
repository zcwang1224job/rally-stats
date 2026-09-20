// Mirrors apps/api/app/domains/schedule/schemas.py — see contracts/schedule-api.md.

import type {
  ServeStationInfo,
  SubstitutionPreview,
  WaitingReason,
} from '../../../core/api/court-live-state.models';

export type { SubstitutionPreview, WaitingReason };
export type Team = 'A' | 'B';
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
  /** 037: the lineup that will play — substitutes included. */
  participants: ParticipantSummary[];
  /** 037: optional so an older backend reads as "no substitutes". */
  substitutions?: SubstitutionPreview[];
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
  /** 038-admin-detailed-scoring: this MATCH's own snapshot of the group
   * setting, not a live read of it — so a mid-match toggle can't change how
   * a match already underway behaves. Tells court-control.component which
   * scoring UI to render (plain +1/-1 vs. score-then-record). Optional so an
   * older backend reads as "simple mode". */
  detailed_scoring_enabled?: boolean;
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
  /** 038-admin-detailed-scoring: the ScoreEvent this mutation created — the
   * backend has always returned it (032-score-then-record), the admin-side
   * model just never declared it. `null` when `applied` is false, or for a
   * mutation that isn't a score change (endMatch()). A `+1`'s caller uses it
   * to attach the shot-placement detail afterwards. */
  score_event_id?: string | null;
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
  /** 037-rest-ready-toggle: resting players stay on the roster, marked.
   * Optional so an older backend (no field) reads as "nobody resting". */
  resting?: boolean;
  resting_since?: string | null;
  /** 037: fixed_partner only — who they team with in this round's matches. */
  partner_roster_entry_id?: string | null;
}

/** 037: PUT …/rest-state response (contracts/rest-state-api.md). */
export interface RestStateResponse {
  roster_entry_id: string;
  resting: boolean;
  resting_since: string | null;
  /** With resting: on court now, resting after this match. */
  currently_playing: boolean;
  /** False when already in the requested state. */
  changed: boolean;
}

export interface ScheduleResponse {
  current_round_number: number;
  scheduling_mechanism: string;
  match_mode: string;
  auto_next_round: boolean;
  /** 只對公平輪替雙打有意義：場地一空就從等最久的人排下一場。 */
  continuous_rotation: boolean;
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
  /** 037：排隊中且含休息中球員的場次——held＝保留等他回來，substitute＝輪到時
   * 由替補上場；其他情況為 null（舊後端沒有這個欄位）。 */
  rest_effect?: RestEffect | null;
}

export type RestEffect = 'held' | 'substitute';

/** 037 FR-021：本輪在等休息中球員的場次。 */
export interface WaitingOnRest {
  match_count: number;
  players: RosterSummary[];
  /** 這一輪已因此無法繼續（沒有比賽在打、剩下的都叫不到）。 */
  stalled: boolean;
}

export interface RoundMatchesResponse {
  round_number: number;
  matches: RoundMatchSummary[];
  /** 還沒打完的場次數（排隊中＋進行中）。 */
  remaining_count: number;
  /** 粗估還要幾分鐘本輪才會打完；沒有剩餘場次時為 null。 */
  estimated_remaining_minutes: number | null;
  /** 本輪完全沒有排到比賽的現役成員（例如固定搭檔人數為奇數時的輪空）；不含休息中的人。 */
  sitting_out: RosterSummary[];
  /** 037：沒有場次在等休息中的球員時為 null。 */
  waiting_on_rest?: WaitingOnRest | null;
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
