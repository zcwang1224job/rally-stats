import { buildLeaderboardCardModel, countPlayers } from './leaderboard-card-model';
import { CREATED_AT, makeHistory, makeStanding, makeStandings } from './testing/history-fixtures';

const context = { createdAt: CREATED_AT };
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

function build(standings = makeStandings(8, { selfAt: 1 }), createdAt: string | null = CREATED_AT) {
  return buildLeaderboardCardModel(makeHistory({ final_standings: standings }), { createdAt });
}

describe('buildLeaderboardCardModel — which rows (041 L1, FR-007)', () => {
  for (const count of [1, 2, 3, 6, 7, 40]) {
    it(`takes the first ${Math.min(count, 6)} of ${count} players who played`, () => {
      const standings = makeStandings(count);
      const model = build(standings)!;

      expect(model.rows.map((r) => r.nickname)).toEqual(
        standings.slice(0, Math.min(count, 6)).map((s) => s.nickname),
      );
    });
  }

  it('keeps the server’s order even when it is not by wins — it never sorts', () => {
    const standings = [
      makeStanding({ roster_entry_id: 'a', nickname: '甲', rank: 1, total_wins: 1, total_losses: 5, total_matches: 6 }),
      makeStanding({ roster_entry_id: 'b', nickname: '乙', rank: 2, total_wins: 9, total_losses: 0, total_matches: 9 }),
      makeStanding({ roster_entry_id: 'c', nickname: '丙', rank: 3, total_wins: 4, total_losses: 4, total_matches: 8 }),
    ];

    expect(build(standings)!.rows.map((r) => r.nickname)).toEqual(['甲', '乙', '丙']);
  });

  it('skips players with no matches wherever they sit, keeping everyone else in order', () => {
    const standings = makeStandings(9, { noMatchesAt: [2, 5] });
    const model = build(standings)!;

    const played = standings.filter((s) => s.total_matches > 0).map((s) => s.nickname);
    expect(model.rows.map((r) => r.nickname)).toEqual(played.slice(0, 6));
    expect(model.rows.map((r) => r.nickname)).not.toContain(standings[2].nickname);
  });
});

describe('buildLeaderboardCardModel — ranks as given (041 L2, L3, FR-008)', () => {
  it('shows ties exactly as the server ranked them', () => {
    const model = build(makeStandings(3, { ranks: [1, 1, 3] }))!;

    expect(model.rows.map((r) => r.rank)).toEqual([1, 1, 3]);
  });

  it('cuts a tie that runs past the sixth row at six rows, ranks untouched', () => {
    const model = build(makeStandings(7, { ranks: [1, 2, 3, 3, 3, 3, 3] }))!;

    expect(model.rows.map((r) => r.rank)).toEqual([1, 2, 3, 3, 3, 3]);
  });

  it('puts the first three rows on the podium, by position not by rank', () => {
    expect(build(makeStandings(7, { ranks: [1, 2, 3, 3, 5, 6, 7] }))!.rows.map((r) => r.podium)).toEqual([
      true, true, true, false, false, false,
    ]);
    expect(build(makeStandings(2))!.rows.map((r) => r.podium)).toEqual([true, true]);
  });

  it('carries wins and losses as given', () => {
    const standings = makeStandings(2);
    const [first] = build(standings)!.rows;

    expect([first.wins, first.losses]).toEqual([standings[0].total_wins, standings[0].total_losses]);
  });
});

describe('buildLeaderboardCardModel — me (041 L4, L5, FR-010)', () => {
  it('marks me in place when I am in the top six, with no extra row', () => {
    const model = build(makeStandings(8, { selfAt: 1 }))!;

    expect(model.rows.map((r) => r.isSelf)).toEqual([false, true, false, false, false, false]);
    expect(model.selfRow).toBeNull();
  });

  it('adds my own row, with my real rank, when I am below the top six', () => {
    const standings = makeStandings(12, { selfAt: 8 });
    const model = build(standings)!;

    expect(model.selfRow).toEqual({
      rank: 9,
      nickname: standings[8].nickname,
      wins: standings[8].total_wins,
      losses: standings[8].total_losses,
      isSelf: true,
      podium: false,
    });
    expect(model.rows.some((r) => r.isSelf)).toBe(false);
  });

  it('adds no row for me when I have not played', () => {
    const model = build(makeStandings(12, { selfAt: 8, noMatchesAt: [8] }))!;

    expect(model.selfRow).toBeNull();
  });

  it('adds no row when I am not in the standings at all', () => {
    expect(build(makeStandings(12))!.selfRow).toBeNull();
  });

  it('never mentions anyone past the sixth row except me', () => {
    const standings = makeStandings(12, { selfAt: 10 });
    const json = JSON.stringify(build(standings));

    for (const [i, row] of standings.entries()) {
      if (i >= 6 && i !== 10) {
        expect(json, row.nickname).not.toContain(row.nickname);
      }
    }
  });
});

describe('buildLeaderboardCardModel — what it leaves out (041 L6, L7, L8, FR-011, FR-021)', () => {
  it('holds no status and no ID of any kind', () => {
    const standings = makeStandings(8, { selfAt: 7, status: { 1: 'left', 7: 'kicked' } });
    const json = JSON.stringify(build(standings));

    expect(json).not.toMatch(/current_status|roster_entry_id|"left"|"kicked"/);
    expect(json).not.toMatch(UUID);
    for (const row of standings) {
      expect(json).not.toContain(`"${row.roster_entry_id}"`);
    }
  });

  it('counts only the players who played', () => {
    const standings = makeStandings(9, { noMatchesAt: [2, 5, 8] });

    expect(build(standings)!.playerCount).toBe(6);
    expect(countPlayers(standings)).toBe(6);
  });

  it('is not available when nobody has played', () => {
    expect(build([])).toBeNull();
    expect(build(makeStandings(4, { noMatchesAt: [0, 1, 2, 3] }))).toBeNull();
  });
});

describe('buildLeaderboardCardModel — the rest (041 L9, L10, FR-031, FR-032)', () => {
  it('builds the same model every time (SC-010)', () => {
    const standings = makeStandings(9, { selfAt: 7 });

    expect(build(standings)).toEqual(build(standings));
  });

  it('keeps the group name and the date, or no date', () => {
    expect(build()!.groupName).toBe('週三羽球團');
    expect(build()!.date).toBe(CREATED_AT);
    expect(build(undefined, null)!.date).toBeNull();
  });

  it('names the file after the card, the date and the group', () => {
    expect(build()!.fileName).toBe('rally-stats-rank-20260916-週三羽球團.png');
    expect(build(undefined, null)!.fileName).toBe('rally-stats-rank-nodate-週三羽球團.png');
  });

  it('keeps the file name safe and short, whatever the group is called', () => {
    const model = buildLeaderboardCardModel(
      makeHistory({ group_name: 'A/B: 週三 羽球*團? "精英" <班> | 很長很長很長很長很長很長很長很長很長很長很長很長' }),
      context,
    )!;
    const name = model.fileName.replace(/^rally-stats-rank-\d{8}-/, '').replace(/\.png$/, '');

    expect(name).not.toMatch(/[/\\:*?"<>|\s]/);
    expect([...name].length).toBeLessThanOrEqual(40);
  });

  it('describes the top three with the server’s ranks in the alt text', () => {
    const standings = makeStandings(5, { ranks: [1, 1, 3, 4, 5] });
    const model = build(standings)!;

    expect(model.altText).toEqual({
      key: 'groupShareCard.leaderboard.altText3',
      params: {
        group: '週三羽球團',
        rank1: 1, name1: standings[0].nickname,
        rank2: 1, name2: standings[1].nickname,
        rank3: 3, name3: standings[2].nickname,
      },
    });
  });

  it('uses the shorter alt text when fewer than three played — no empty names', () => {
    const one = build(makeStandings(1))!;
    const two = build(makeStandings(2))!;

    expect(one.altText.key).toBe('groupShareCard.leaderboard.altText1');
    expect(Object.keys(one.altText.params).sort()).toEqual(['group', 'name1', 'rank1']);
    expect(two.altText.key).toBe('groupShareCard.leaderboard.altText2');
    for (const value of Object.values(two.altText.params)) {
      expect(String(value).length).toBeGreaterThan(0);
    }
  });
});
