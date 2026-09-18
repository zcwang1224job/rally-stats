// Mirrors apps/api/app/domains/group/schemas.py (005-member-view additions)
// — see contracts/member-view-api.md. `rounds` keys are round numbers, but
// arrive as JSON object keys (i.e. strings) — index with String(roundNumber).

import { ParticipantSummary, Team } from '../../features/group-admin/schedule-management/schedule.models';
import { EndingType } from './court-live-state.models';

// A per-round *tally*, not a single outcome: singles fair_rotation's full
// round-robin can complete several matches for one Member within the same
// round_number before Next Round is pressed (011-round-robin-scheduling),
// so `wins`/`losses` count every completed match that round. `left` means
// this Member had already left/been kicked before the round started
// (irreversible from then on) — mutually exclusive with ever accumulating
// wins/losses for that round. did_not_play is simply `wins === 0 && losses
// === 0 && !left`.
export interface RoundRecord {
  wins: number;
  losses: number;
  left: boolean;
}

export interface MemberStandingRow {
  roster_entry_id: string;
  nickname: string;
  current_status: 'active' | 'left' | 'kicked';
  rounds: Record<string, RoundRecord>;
  // 018-group-leaderboard: standard competition ranking ("1224") over
  // total_wins, computed server-side — MUST NOT be re-derived/re-sorted
  // client-side (constitution X). `members` in GroupStandingsResponse
  // already arrives pre-sorted by rank.
  rank: number;
  total_wins: number;
  total_losses: number;
}

export interface GroupStandingsResponse {
  current_round_number: number;
  rounds: number[];
  members: MemberStandingRow[];
}

// 019-group-final-standings: the "我的團" history page's final team
// ranking row — unlike MemberStandingRow (the live standings tab), this
// covers every ever-participant (active/left/kicked, member or guest,
// multiple stints of the same member merged into one row) and has no
// per-round breakdown, only cumulative totals.
export interface FinalStandingRow {
  roster_entry_id: string;
  nickname: string;
  current_status: 'active' | 'left' | 'kicked';
  // Computed server-side (research.md #4) — render directly, MUST NOT be
  // re-derived by comparing IDs client-side (constitution X).
  is_self: boolean;
  rank: number;
  total_matches: number;
  total_wins: number;
  total_losses: number;
}

export interface MatchRecordSummary {
  match_id: string;
  round_number: number;
  team_a: ParticipantSummary[];
  team_b: ParticipantSummary[];
  score_a: number;
  score_b: number;
  winner_team: Team;
  started_at: string | null;
  ended_at: string | null;
}

export interface GroupMatchRecordsResponse {
  matches: MatchRecordSummary[];
  page: number;
  total_pages: number;
}

export interface MemberMatchRecordSummary extends MatchRecordSummary {
  group_id: string;
  group_name: string;
  won: boolean;
}

// 032-match-record-scoring-stats: a per-point snapshot of "who scored, who
// was at fault, where it landed" — read-only projection of an existing
// ShotPlacementRecord row (031/032-shot-placement-scoring). Every field
// independently optional (research.md data-model.md); `null` sub-fields are
// simply not shown, never inferred.
export interface ShotPlacementDetail {
  scoring_roster_entry_id: string | null;
  scoring_nickname: string | null;
  losing_roster_entry_id: string | null;
  losing_nickname: string | null;
  landing_x: number | null;
  landing_y: number | null;
  // 035-point-ending-type: how the rally ended; null = not recorded
  // (every pre-035 point included). Present whatever record_completeness
  // is — a per-point fact, not a derivation.
  ending_type: EndingType | null;
}

// 016-match-score-timeline: one +1/-1 scoring action, with its time
// expressed as seconds elapsed since the match started (research.md #3 —
// deliberately not a wall-clock timestamp).
export interface ScoreEventSummary {
  side: Team;
  delta: 1 | -1;
  score_a: number;
  score_b: number;
  elapsed_seconds: number;
  // research.md (032) Decision 2: null for a -1 event, a +1 event with no
  // ShotPlacementRecord at all, or one whose five fields are all null.
  detail: ShotPlacementDetail | null;
}

// 032-match-record-scoring-stats: one match participant's aggregate across
// every ShotPlacementRecord row in this match.
export interface PlayerScoringStat {
  roster_entry_id: string;
  nickname: string;
  team: Team;
  scored_count: number;
  fault_count: number;
}

// 033-match-record-derived-stats: counts only — the percentage is derived
// here on the frontend, and a zero total renders as "—" rather than 0%.
export interface ServeCounts {
  serve_points_won: number;
  serve_points_total: number;
  receive_points_won: number;
  receive_points_total: number;
}

export interface TeamServeStat extends ServeCounts {
  team: Team;
}

export interface PlayerServeStat extends ServeCounts {
  roster_entry_id: string;
  nickname: string;
  team: Team;
}

export interface ServeStats {
  teams: TeamServeStat[]; // always [A, B]
  // Doubles: every participant, all-zero ones included. Singles: [] — the
  // player level would only repeat the team level.
  players: PlayerServeStat[];
  // Points whose server couldn't be determined; always >= 1 because the
  // pre-match serve draw is never persisted (so the first point is unknown).
  excluded_points: number;
}

export interface ScoringRun {
  team: Team;
  length: number;
  // Score right BEFORE the run's first point / right AFTER its last; all
  // four null when length is 0.
  start_score_a: number | null;
  start_score_b: number | null;
  end_score_a: number | null;
  end_score_b: number | null;
}

export interface MaxLead {
  team: Team;
  margin: number;
  // Score the first time this margin was reached; null when margin is 0.
  score_a: number | null;
  score_b: number | null;
}

export interface LeadChange {
  new_leader: Team;
  score_a: number;
  score_b: number;
}

export interface MomentumStats {
  longest_runs: ScoringRun[]; // always [A, B]
  max_leads: MaxLead[]; // always [A, B]
  lead_changes: LeadChange[];
}

export interface TempoStats {
  average_seconds: number;
  counted_points: number;
  longest: { seconds: number; score_a: number; score_b: number };
}

export interface LandingPoint {
  x: number;
  y: number;
}

export interface PlayerLandingDistribution {
  roster_entry_id: string;
  nickname: string;
  team: Team;
  scored: LandingPoint[];
  // Every point credited to this player, plotted or not — the denominator
  // shown next to `scored`. Same meaning for lost/lost_total.
  scored_total: number;
  lost: LandingPoint[];
  lost_total: number;
}

// 034-clutch-points-player-dashboard: how each TEAM did when it mattered.
// Every phase/state is judged by the score a point STARTED from.
export interface ClutchPhaseTotals {
  won: number;
  total: number;
}

export interface ClutchPhaseCounts extends ClutchPhaseTotals {
  team: Team;
}

export interface ClutchMatchPoints {
  team: Team;
  held: number;
  // Which of this team's match points (1-based) ended the match; null for
  // the loser.
  converted_on: number | null;
  saved: number;
}

// A `total` of 0 means "never in that state" — shown as "0/0 —", never 0%.
export interface ClutchStateCounts {
  team: Team;
  leading: ClutchPhaseTotals;
  tied: ClutchPhaseTotals;
  trailing: ClutchPhaseTotals;
}

export interface ClutchComeback {
  winner: Team;
  max_deficit: number;
  score_a: number;
  score_b: number;
}

export interface ClutchStats {
  endgame_from: number | null; // null: target too low for the phase to apply
  endgame: ClutchPhaseCounts[] | null; // [A, B]; null iff endgame_from is
  deuce: ClutchPhaseCounts[] | null; // [A, B]; null: never reached deuce
  match_points: ClutchMatchPoints[]; // always [A, B]
  by_state: ClutchStateCounts[]; // always [A, B]
  comeback: ClutchComeback | null; // null: the winner never trailed
}

// 035-point-ending-type: the per-match split of points into winners and
// errors. Mirrors group/schemas.py's EndingStats.
export interface ErrorsByType {
  out: number;
  net: number;
  serve_fault: number;
  other_error: number;
}

export interface TeamEndingStat {
  team: Team;
  winners: number;
  // Errors THIS team committed (= points the other team got by error).
  errors: number;
  errors_by_type: ErrorsByType;
}

// winners + opponent_errors + scored_unrecorded = this player's
// player_stats.scored_count; the lost triple likewise = fault_count.
export interface PlayerEndingStat {
  roster_entry_id: string;
  nickname: string;
  team: Team;
  winners: number;
  opponent_errors: number;
  scored_unrecorded: number;
  beaten_by_winners: number;
  own_errors: number;
  lost_unrecorded: number;
}

export interface EndingStats {
  // Coverage: effective points with a recorded ending, out of all.
  recorded_points: number;
  total_points: number;
  teams: TeamEndingStat[]; // always [A, B]
  players: PlayerEndingStat[]; // every participant, team_a + team_b
}

// `record_completeness` distinguishes three states purely derived from
// the events themselves (research.md #3, no deploy-timestamp dependency):
// "complete" (first event is the match's real first point), "partial"
// (recording started mid-match), "none" (no events at all — a match
// completed before this feature shipped).
export interface MatchRecordDetailResponse extends MatchRecordSummary {
  record_completeness: 'complete' | 'partial' | 'none';
  events: ScoreEventSummary[];
  // research.md (032) Decision 4: `[]` is the single signal for "no player
  // was ever recorded in this match"; non-empty always lists EVERY
  // participant in team_a + team_b, zero counts included.
  player_stats: PlayerScoringStat[];
  // 033-match-record-derived-stats: four independent derivations. null / []
  // IS the "no data" signal (shown as a notice) — never an all-zero
  // structure. All four are empty unless record_completeness is "complete".
  serve_stats: ServeStats | null;
  momentum_stats: MomentumStats | null;
  tempo_stats: TempoStats | null;
  landing_distribution: PlayerLandingDistribution[];
  // 034: same "complete record only" rule as the four above.
  clutch_stats: ClutchStats | null;
  // 035: same rule again, and null as well when not one point of the
  // match recorded an ending (every pre-035 match).
  ending_stats: EndingStats | null;
}

export interface RoundWinRatePoint {
  round_number: number;
  wins: number;
  losses: number;
  win_rate: number;
}

export interface OpponentRecord {
  nickname: string;
  wins: number;
  losses: number;
  matches: number;
  win_rate: number;
}

export interface MemberMatchRecordsResponse {
  matches: MemberMatchRecordSummary[];
  total_matches: number;
  total_wins: number;
  total_losses: number;
  win_rate: number;
  round_win_rates: RoundWinRatePoint[];
  opponent_records: OpponentRecord[];
  page: number;
  total_pages: number;
}

export type MatchRecordResultFilter = 'win' | 'loss';
export type MatchRecordScoreComparison = 'gt' | 'eq' | 'lt';

export interface MemberMatchRecordFilters {
  opponent1?: string;
  opponent2?: string;
  partner?: string;
  result?: MatchRecordResultFilter;
  date_from?: string;
  date_to?: string;
  round_from?: number;
  round_to?: number;
  self_score_cmp?: MatchRecordScoreComparison;
  self_score?: number;
  opponent_score_cmp?: MatchRecordScoreComparison;
  opponent_score?: number;
  match_mode?: 'singles' | 'doubles';
}

export interface LeaveGroupResponse {
  roster_entry_id: string;
  status: 'left';
}
