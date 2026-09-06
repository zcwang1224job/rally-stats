// Mirrors apps/api/app/domains/group/schemas.py (005-member-view additions)
// — see contracts/member-view-api.md. `rounds` keys are round numbers, but
// arrive as JSON object keys (i.e. strings) — index with String(roundNumber).

import { ParticipantSummary, Team } from '../../features/group-admin/schedule-management/schedule.models';

export type RoundStatus = 'won' | 'lost' | 'did_not_play' | 'left';

export interface MemberStandingRow {
  roster_entry_id: string;
  nickname: string;
  current_status: 'active' | 'left' | 'kicked';
  rounds: Record<string, RoundStatus>;
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
}

export interface GroupMatchRecordsResponse {
  matches: MatchRecordSummary[];
  page: number;
  total_pages: number;
}

export interface MemberMatchRecordSummary extends MatchRecordSummary {
  group_id: string;
  group_name: string;
}

export interface MemberMatchRecordsResponse {
  matches: MemberMatchRecordSummary[];
  total_matches: number;
  total_wins: number;
  total_losses: number;
  win_rate: number;
  page: number;
  total_pages: number;
}

export interface LeaveGroupResponse {
  roster_entry_id: string;
  status: 'left';
}
