import { MemberGroupHistoryResponse } from '../api/friend.models';
import { formatPercent } from '../match-record-detail/ratio-format';
import { buildMyStatsCardModel } from './my-stats-card-model';
import {
  CREATED_AT,
  makeHistory,
  makeOpponents,
  makeRounds,
  makeStandings,
} from './testing/history-fixtures';

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

function stats(overrides: Partial<MemberGroupHistoryResponse['my_stats']> = {}) {
  return { ...makeHistory().my_stats, ...overrides };
}

function build(history = makeHistory(), createdAt: string | null = CREATED_AT) {
  return buildMyStatsCardModel(history, { createdAt });
}

describe('buildMyStatsCardModel — when it is offered (041 M1, FR-013)', () => {
  it('is not offered when I have played no match in the group', () => {
    const history = makeHistory({
      my_stats: stats({ total_matches: 0, total_wins: 0, total_losses: 0, win_rate: 0 }),
    });

    expect(build(history)).toBeNull();
  });

  it('is offered after a single match', () => {
    const history = makeHistory({
      my_stats: stats({ total_matches: 1, total_wins: 1, total_losses: 0, win_rate: 1 }),
    });

    expect(build(history)).not.toBeNull();
  });
});

describe('buildMyStatsCardModel — the numbers, as the page shows them (041 M2, M3, FR-014, FR-017)', () => {
  for (const rate of [0, 0.6, 2 / 3, 1]) {
    it(`writes a ${rate} win rate exactly as the page does`, () => {
      const model = build(makeHistory({ my_stats: stats({ win_rate: rate }) }))!;

      expect(model.winRate).toBe(formatPercent(rate));
    });
  }

  it('carries wins, losses and matches as given', () => {
    const model = build()!;

    expect([model.wins, model.losses, model.matches]).toEqual([6, 4, 10]);
  });

  it('takes my rank and name from my standings row, out of the players who played', () => {
    const standings = makeStandings(9, { selfAt: 4, noMatchesAt: [7], ranks: [1, 2, 2, 4, 5, 6, 7, 8, 9] });
    const model = build(makeHistory({ final_standings: standings }))!;

    expect(model.standing).toEqual({ rank: 5, playerCount: 8 });
    expect(model.nickname).toBe(standings[4].nickname);
  });

  it('leaves out my rank and name when I am not in the standings', () => {
    const model = build(makeHistory({ final_standings: makeStandings(5) }))!;

    expect(model.standing).toBeNull();
    expect(model.nickname).toBeNull();
  });
});

describe('buildMyStatsCardModel — the round trend (041 M4, FR-015)', () => {
  it('leaves the trend out with fewer than two rounds', () => {
    expect(build(makeHistory({ my_stats: stats({ round_win_rates: [] }) }))!.trend).toBeNull();
    expect(build(makeHistory({ my_stats: stats({ round_win_rates: makeRounds([1]) }) }))!.trend).toBeNull();
  });

  it('plots each round on the page’s fixed 0–100% axis (0 at the top)', () => {
    const model = build(makeHistory({ my_stats: stats({ round_win_rates: makeRounds([0.5, 1, 0]) }) }))!;

    expect(model.trend).toEqual([
      { x: 0, y: 50 },
      { x: 50, y: 0 },
      { x: 100, y: 100 },
    ]);
  });

  it('keeps a flat trend where its rate is — no rescaling', () => {
    const model = build(makeHistory({ my_stats: stats({ round_win_rates: makeRounds([0.6, 0.6, 0.6]) }) }))!;

    expect(model.trend!.map((p) => p.y)).toEqual([40, 40, 40]);
  });
});

describe('buildMyStatsCardModel — opponents (041 M5, FR-016)', () => {
  for (const count of [0, 1, 3, 5]) {
    it(`shows the first ${Math.min(count, 3)} of ${count} opponents, in the page’s order`, () => {
      const opponents = makeOpponents(count);
      const model = build(makeHistory({ my_stats: stats({ opponent_records: opponents }) }))!;

      expect(model.opponents).toEqual(
        opponents.slice(0, 3).map((o) => ({ nickname: o.nickname, wins: o.wins, losses: o.losses })),
      );
    });
  }

  it('never re-orders them — not by wins, not by anything', () => {
    const opponents = [
      { nickname: '甲', wins: 0, losses: 5, matches: 5, win_rate: 0 },
      { nickname: '乙', wins: 9, losses: 0, matches: 9, win_rate: 1 },
      { nickname: '丙', wins: 1, losses: 1, matches: 2, win_rate: 0.5 },
    ];
    const model = build(makeHistory({ my_stats: stats({ opponent_records: opponents }) }))!;

    expect(model.opponents.map((o) => o.nickname)).toEqual(['甲', '乙', '丙']);
  });
});

describe('buildMyStatsCardModel — the rest (041 M6, FR-021, FR-031, FR-032)', () => {
  it('keeps the date, or none', () => {
    expect(build()!.date).toBe(CREATED_AT);
    expect(build(undefined, null)!.date).toBeNull();
  });

  it('names the file after the card, the date and the group', () => {
    expect(build()!.fileName).toBe('rally-stats-me-20260916-週三羽球團.png');
    expect(build(undefined, null)!.fileName).toBe('rally-stats-me-nodate-週三羽球團.png');
  });

  it('describes the group, my win rate and record in the alt text', () => {
    expect(build()!.altText).toEqual({
      key: 'groupShareCard.myStats.altText',
      params: { group: '週三羽球團', winRate: formatPercent(0.6), wins: 6, losses: 4 },
    });
  });

  it('builds the same model every time and holds no ID', () => {
    const history = makeHistory();
    const json = JSON.stringify(build(history));

    expect(build(history)).toEqual(build(history));
    expect(json).not.toMatch(UUID);
    expect(json).not.toMatch(/roster_entry_id|"r-\d+"/);
  });
});
