// Mirrors apps/api/app/domains/group/schemas.py (005-member-view additions)
// — see contracts/member-view-api.md. `rounds` keys are round numbers, but
// arrive as JSON object keys (i.e. strings) — index with String(roundNumber).

import { ParticipantSummary, Team } from '../../features/group-admin/schedule-management/schedule.models';

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

// 016-match-score-timeline: one +1/-1 scoring action, with its time
// expressed as seconds elapsed since the match started (research.md #3 —
// deliberately not a wall-clock timestamp).
export interface ScoreEventSummary {
  side: Team;
  delta: 1 | -1;
  score_a: number;
  score_b: number;
  elapsed_seconds: number;
}

// `record_completeness` distinguishes three states purely derived from
// the events themselves (research.md #3, no deploy-timestamp dependency):
// "complete" (first event is the match's real first point), "partial"
// (recording started mid-match), "none" (no events at all — a match
// completed before this feature shipped).
export interface MatchRecordDetailResponse extends MatchRecordSummary {
  record_completeness: 'complete' | 'partial' | 'none';
  events: ScoreEventSummary[];
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
