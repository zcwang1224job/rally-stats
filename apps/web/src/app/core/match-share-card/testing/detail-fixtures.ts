import {
  ClutchStats,
  EndingStats,
  MatchRecordDetailResponse,
  MomentumStats,
  TempoStats,
} from '../../api/group-member-view.models';
import { Team } from '../../../features/group-admin/schedule-management/schedule.models';

/** 040-match-share-card: a valid match detail for specs — 21-point doubles,
 * A wins 21:17, complete record, every derived block empty. Each spec adds
 * only the stats its case needs. */
export function makeDetail(
  overrides: Partial<MatchRecordDetailResponse> = {},
): MatchRecordDetailResponse {
  return {
    match_id: 'm1',
    round_number: 3,
    team_a: [
      { roster_entry_id: 'a1', nickname: '王小明', team: 'A' },
      { roster_entry_id: 'a2', nickname: '陳大華', team: 'A' },
    ],
    team_b: [
      { roster_entry_id: 'b1', nickname: '林小美', team: 'B' },
      { roster_entry_id: 'b2', nickname: '張阿強', team: 'B' },
    ],
    score_a: 21,
    score_b: 17,
    winner_team: 'A',
    started_at: '2026-09-21T11:02:10Z',
    ended_at: '2026-09-21T11:20:42Z',
    target_score: 21,
    record_completeness: 'complete',
    events: [
      { side: 'A', delta: 1, score_a: 1, score_b: 0, elapsed_seconds: 20, detail: null },
      { side: 'B', delta: 1, score_a: 1, score_b: 1, elapsed_seconds: 45, detail: null },
      { side: 'A', delta: 1, score_a: 21, score_b: 17, elapsed_seconds: 1112, detail: null },
    ],
    player_stats: [],
    serve_stats: null,
    momentum_stats: null,
    tempo_stats: null,
    landing_distribution: [],
    clutch_stats: null,
    ending_stats: null,
    ...overrides,
  };
}

export function makeSingles(overrides: Partial<MatchRecordDetailResponse> = {}) {
  return makeDetail({
    team_a: [{ roster_entry_id: 'a1', nickname: '王小明', team: 'A' }],
    team_b: [{ roster_entry_id: 'b1', nickname: '林小美', team: 'B' }],
    ...overrides,
  });
}

export function makePartial(overrides: Partial<MatchRecordDetailResponse> = {}) {
  return makeDetail({
    record_completeness: 'partial',
    events: [
      { side: 'A', delta: 1, score_a: 12, score_b: 9, elapsed_seconds: 600, detail: null },
      { side: 'A', delta: 1, score_a: 21, score_b: 17, elapsed_seconds: 1112, detail: null },
    ],
    ...overrides,
  });
}

export function makeNone(overrides: Partial<MatchRecordDetailResponse> = {}) {
  return makeDetail({ record_completeness: 'none', events: [], ...overrides });
}

/** Momentum with the given longest runs (A, B) and lead-change count. */
export function withMomentum(runA: number, runB: number, leadChanges = 0): MomentumStats {
  const run = (team: Team, length: number) => ({
    team,
    length,
    start_score_a: length ? 0 : null,
    start_score_b: length ? 0 : null,
    end_score_a: length ? 1 : null,
    end_score_b: length ? 1 : null,
  });
  return {
    longest_runs: [run('A', runA), run('B', runB)],
    max_leads: [
      { team: 'A', margin: 0, score_a: null, score_b: null },
      { team: 'B', margin: 0, score_a: null, score_b: null },
    ],
    lead_changes: Array.from({ length: leadChanges }, (_, i) => ({
      new_leader: (i % 2 === 0 ? 'B' : 'A') as Team,
      score_a: i,
      score_b: i + 1,
    })),
  };
}

export interface ClutchOptions {
  comeback?: { winner: Team; maxDeficit: number };
  savedA?: number;
  savedB?: number;
  deuce?: boolean;
}

export function withClutch(options: ClutchOptions = {}): ClutchStats {
  const zero = { won: 0, total: 0 };
  return {
    endgame_from: 18,
    endgame: [
      { team: 'A', ...zero },
      { team: 'B', ...zero },
    ],
    deuce: options.deuce
      ? [
          { team: 'A', won: 2, total: 3 },
          { team: 'B', won: 1, total: 3 },
        ]
      : null,
    match_points: [
      { team: 'A', held: 1, converted_on: 1, saved: options.savedA ?? 0 },
      { team: 'B', held: 0, converted_on: null, saved: options.savedB ?? 0 },
    ],
    by_state: [
      { team: 'A', leading: zero, tied: zero, trailing: zero },
      { team: 'B', leading: zero, tied: zero, trailing: zero },
    ],
    comeback: options.comeback
      ? {
          winner: options.comeback.winner,
          max_deficit: options.comeback.maxDeficit,
          score_a: 2,
          score_b: 2 + options.comeback.maxDeficit,
        }
      : null,
  };
}

/** Ending stats: winners per team, and how many of all points had an
 * ending recorded (`recorded` of `total`). */
export function withEnding(
  winnersA: number,
  winnersB: number,
  recorded: number,
  total: number,
): EndingStats {
  const noErrors = { out: 0, net: 0, serve_fault: 0, other_error: 0 };
  return {
    recorded_points: recorded,
    total_points: total,
    teams: [
      { team: 'A', winners: winnersA, errors: 0, errors_by_type: noErrors },
      { team: 'B', winners: winnersB, errors: 0, errors_by_type: noErrors },
    ],
    players: [],
  };
}

export function withTempo(averageSeconds: number): TempoStats {
  return {
    average_seconds: averageSeconds,
    counted_points: 38,
    longest: { seconds: 70, score_a: 15, score_b: 14 },
  };
}
