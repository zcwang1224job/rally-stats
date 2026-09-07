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
}

export interface LeaveGroupResponse {
  roster_entry_id: string;
  status: 'left';
}
