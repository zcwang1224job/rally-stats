// Mirrors the 007-live-scoreboard schemas in
// apps/api/app/domains/schedule/schemas.py (data-model.md).

import { CourtLinkType } from './court-link.models';

export type Team = 'A' | 'B';
export type WaitingReason = 'manual_assignment' | 'no_queued_match';

export interface ParticipantSummary {
  roster_entry_id: string;
  nickname: string;
  team: Team;
}

export interface MatchLiveDetail {
  match_id: string;
  status: 'in_progress';
  score_a: number;
  score_b: number;
  participants: ParticipantSummary[];
}

export interface NextUpPreview {
  match_id: string;
  participants: ParticipantSummary[];
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
}
