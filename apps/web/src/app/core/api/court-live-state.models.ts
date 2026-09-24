// Mirrors the 007-live-scoreboard schemas in
// apps/api/app/domains/schedule/schemas.py (data-model.md).

import { CourtLinkType } from './court-link.models';

export type Team = 'A' | 'B';
/** 037-rest-ready-toggle adds held_for_rest and not_enough_ready. Display
 * goes through `waitingReasonKey()`, which falls back for unknown values. */
export type WaitingReason =
  | 'manual_assignment'
  | 'no_queued_match'
  | 'held_for_rest'
  | 'not_enough_ready';

/** 037: who plays in place of whom when a previewed match is called. */
export interface SubstitutionPreview {
  resting: { roster_entry_id: string; nickname: string };
  substitute: { roster_entry_id: string; nickname: string };
}

// 035-point-ending-type: how a rally ended — 'winner' is the scorer's doing,
// the other four are the loser's errors. Mirrors `EndingType` in
// schedule/schemas.py; the backend contract test sends every value of
// ENDING_TYPES in this order, which is the check between the two sides.
export type EndingType = 'winner' | 'out' | 'net' | 'serve_fault' | 'other_error';
/** The five kinds in their fixed display order (the picker's chip row). */
export const ENDING_TYPES: readonly EndingType[] = [
  'winner',
  'out',
  'net',
  'serve_fault',
  'other_error',
];

export interface ParticipantSummary {
  roster_entry_id: string;
  nickname: string;
  team: Team;
}

// 029-serve-rotation-display: who's serving and where everyone stands right
// now — mirrors 030-score-serve-record's ScoreServeRecord column shape 1:1.
export interface ServeStationInfo {
  server_roster_entry_id: string;
  server_team: Team;
  team_a_right_roster_entry_id: string | null;
  team_a_left_roster_entry_id: string | null;
  team_b_right_roster_entry_id: string | null;
  team_b_left_roster_entry_id: string | null;
}

export interface MatchLiveDetail {
  match_id: string;
  status: 'in_progress';
  score_a: number;
  score_b: number;
  participants: ParticipantSummary[];
  // null when the match has no serve state yet (a match created before
  // 030-score-serve-record's migration).
  serve: ServeStationInfo | null;
  // 031-shot-placement-scoring: this match's OWN snapshot, not a live read
  // of the group's current setting — decides whether to render the plain
  // +1/-1 buttons or the tap-the-court picker for this specific match.
  detailed_scoring_enabled: boolean;
  /** 039-match-point-confirm: this match's own scoring rules, so a screen
   * can tell whether the next point would END the match and warn first.
   * Snapshots, like detailed_scoring_enabled. Optional so an older backend
   * reads as `undefined`, which isMatchPoint() treats as "never warn".
   * `deuce_threshold` is absent on purpose — it takes no part in the win
   * test (see core/match-point.ts). */
  target_score?: number;
  cap_score?: number;
}

export interface NextUpPreview {
  match_id: string;
  /** 037: the lineup that will play — substitutes included. */
  participants: ParticipantSummary[];
  /** 037: optional so an older backend reads as "no substitutes". */
  substitutions?: SubstitutionPreview[];
}

export interface CourtLiveState {
  court_id: string;
  round_number: number;
  current_match: MatchLiveDetail | null;
  waiting_reason: WaitingReason | null;
  next_up: NextUpPreview | null;
}

export interface CourtStateResponse {
  court_id: string;
  group_id: string;
  name: string;
  link_type: CourtLinkType;
  link_version: number;
  deleted: boolean;
  group_disbanded: boolean;
  // 018-plan-then-start follow-up: the group's admin-controlled opt-in for
  // letting a `scoreboard` link also score — always the group's actual
  // setting regardless of this response's own `link_type`.
  scoreboard_scoring_enabled: boolean;
  round_number: number;
  current_match: MatchLiveDetail | null;
  waiting_reason: WaitingReason | null;
  next_up: NextUpPreview | null;
}

export interface AllCourtsLiveState {
  group_id: string;
  round_number: number;
  courts: CourtLiveState[];
}

export interface ScoreMutationResult {
  applied: boolean;
  match_id: string;
  status: 'in_progress' | 'completed' | 'abandoned';
  score_a: number;
  score_b: number;
  winner_team: Team | null;
  // 032-score-then-record: the ScoreEvent this mutation created — null when
  // `applied` is false, or for a mutation that isn't a score change (e.g.
  // ending a match). A `+1`'s caller uses this to attach a
  // ShotPlacementRecord afterward without blocking the score itself on it.
  score_event_id: string | null;
  // feature/control-panel-scoreboard-style: lets the acting client patch its
  // own station display directly from this response instead of waiting on
  // its own match.scoreUpdated realtime echo — null when the match just
  // ended this point (no more serve state to show) or the mutation wasn't
  // applied.
  serve: ServeStationInfo | null;
}

export interface ShotPlacementAttachResponse {
  recorded: boolean;
}
