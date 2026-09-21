import { MemberGroupHistoryResponse } from '../../api/friend.models';
import { FinalStandingRow, OpponentRecord, RoundWinRatePoint } from '../../api/group-member-view.models';

/** A UTC noon timestamp, so the date in file names is the same in every
 * time zone a test may run in. */
export const CREATED_AT = '2026-09-16T12:00:00Z';

const NICKNAMES = [
  '王小明', '陳大華', '林小美', '張阿強', '李文文', '黃志豪', '吳佳穎', '周建宏',
  '鄭雅婷', '謝宗翰', '蔡依林', '許家豪', '劉怡君', '楊承翰', '洪詩涵', '邱冠宇',
];

export function makeStanding(overrides: Partial<FinalStandingRow> = {}): FinalStandingRow {
  return {
    roster_entry_id: 'r-1',
    nickname: '王小明',
    current_status: 'active',
    is_self: false,
    rank: 1,
    total_matches: 8,
    total_wins: 6,
    total_losses: 2,
    ...overrides,
  };
}

export interface StandingsOptions {
  /** 0-based row that is the viewer. */
  selfAt?: number;
  /** Ranks to use instead of 1..N (the server's standard competition ranks). */
  ranks?: number[];
  /** 0-based rows that have played no match. */
  noMatchesAt?: number[];
  /** 0-based rows with a left/kicked status. */
  status?: Record<number, FinalStandingRow['current_status']>;
}

/** N rows already in the server's order (wins descending). */
export function makeStandings(count: number, options: StandingsOptions = {}): FinalStandingRow[] {
  return Array.from({ length: count }, (_, i) => {
    const played = !(options.noMatchesAt ?? []).includes(i);
    const wins = played ? Math.max(0, count - i) : 0;
    const losses = played ? i + 1 : 0;
    return makeStanding({
      roster_entry_id: `r-${i + 1}`,
      nickname: NICKNAMES[i % NICKNAMES.length] + (i >= NICKNAMES.length ? String(i) : ''),
      current_status: options.status?.[i] ?? 'active',
      is_self: options.selfAt === i,
      rank: options.ranks?.[i] ?? i + 1,
      total_matches: wins + losses,
      total_wins: wins,
      total_losses: losses,
    });
  });
}

export function makeRounds(rates: number[]): RoundWinRatePoint[] {
  return rates.map((rate, i) => ({
    round_number: i + 1,
    wins: Math.round(rate * 4),
    losses: 4 - Math.round(rate * 4),
    win_rate: rate,
  }));
}

export function makeOpponents(count: number): OpponentRecord[] {
  return Array.from({ length: count }, (_, i) => ({
    nickname: NICKNAMES[(i + 8) % NICKNAMES.length],
    wins: count - i,
    losses: 1,
    matches: count - i + 1,
    win_rate: (count - i) / (count - i + 1),
  }));
}

export function makeHistory(
  overrides: Partial<MemberGroupHistoryResponse> = {},
): MemberGroupHistoryResponse {
  return {
    group_id: 'g-1',
    group_name: '週三羽球團',
    my_stats: {
      total_matches: 10,
      total_wins: 6,
      total_losses: 4,
      win_rate: 0.6,
      round_win_rates: makeRounds([0.5, 0.75, 0.5]),
      opponent_records: makeOpponents(4),
    },
    final_standings: makeStandings(8, { selfAt: 1 }),
    matches: [],
    page: 1,
    total_pages: 1,
    player_records: [],
    ...overrides,
  };
}
