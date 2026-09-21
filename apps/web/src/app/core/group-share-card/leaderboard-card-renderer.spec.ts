import { formatDate } from '@angular/common';
import { SHARE_CARD_PADDING, SHARE_CARD_WIDTH, ShareCardText } from '../share-card/share-card-canvas';
import { SHARE_CARD_MIDDLE_BOTTOM } from '../share-card/share-card-layout';
import { ShareCardRenderEnv } from '../share-card/share-card-option';
import { SHARE_PALETTES } from '../share-card/share-card-palette';
import { footerOpCount, testFooter } from '../share-card/testing/footer-ops';
import { RecordingContext } from '../share-card/testing/recording-context';
import { MEDAL_COLORS } from './group-share-card-palette';
import { buildLeaderboardCardModel } from './leaderboard-card-model';
import { renderLeaderboardCard } from './leaderboard-card-renderer';
import { CREATED_AT, makeHistory, makeStanding, makeStandings } from './testing/history-fixtures';

const ZH_DATE = 'yyyy/M/d';

/** The real date pattern, brand and record wording (a record as long as
 * the real one, so the column fits as it would); `name(param,…)` for
 * everything else. */
const record = (wins: number, losses: number) => `${wins} 勝 ${losses} 敗`;
const fakeText: ShareCardText = (key, params) => {
  if (key === 'groupShareCard.leaderboard.record') {
    return record(Number(params?.['wins']), Number(params?.['losses']));
  }
  if (key === 'shareCard.dateFormat') {
    return ZH_DATE;
  }
  if (key === 'shareCard.brand') {
    return 'Rally Stats';
  }
  const name = key.split('.').pop();
  return `${name}(${Object.values(params ?? {}).join(',')})`;
};

function env(theme: 'light' | 'dark' = 'light'): ShareCardRenderEnv {
  return {
    palette: SHARE_PALETTES[theme],
    text: fakeText,
    fonts: { base: 'sans-serif', score: 'monospace' },
    footer: testFooter(),
  };
}

function draw(
  standings = makeStandings(8, { selfAt: 1 }),
  options: { theme?: 'light' | 'dark'; createdAt?: string | null; groupName?: string } = {},
): RecordingContext {
  const model = buildLeaderboardCardModel(
    makeHistory({ final_standings: standings, group_name: options.groupName ?? '週三羽球團' }),
    { createdAt: options.createdAt === undefined ? CREATED_AT : options.createdAt },
  )!;
  const ctx = new RecordingContext();
  renderLeaderboardCard(ctx, model, env(options.theme));
  return ctx;
}

/** Bottom of everything between the background and the footer. */
function middleBottom(ctx: RecordingContext): number {
  const e = env();
  return ctx.bottomEdge({ skipFirst: 1, skipLast: footerOpCount(e.footer, e) });
}

describe('renderLeaderboardCard — what it shows (041 US1, FR-006, FR-012)', () => {
  it('writes the group, the title, the date and how many played', () => {
    const texts = draw().texts().join('\n');

    expect(texts).toContain('週三羽球團');
    expect(texts).toContain('title()');
    expect(texts).toContain(formatDate(CREATED_AT, ZH_DATE, 'en-US'));
    expect(texts).toContain('playerCount(8)');
  });

  it('leaves the date out, and only the date, when there is none', () => {
    const texts = draw(undefined, { createdAt: null }).texts().join('\n');

    expect(texts).not.toMatch(/\d{4}\/\d{1,2}\/\d{1,2}/);
    expect(texts).toContain('title() · playerCount(8)');
  });

  it('writes every row’s rank, name and record', () => {
    const standings = makeStandings(8, { selfAt: 1 });
    const ctx = draw(standings);

    for (const row of standings.slice(0, 6)) {
      expect(ctx.texts()).toContain(String(row.rank));
      expect(ctx.texts()).toContain(row.nickname);
      expect(ctx.texts()).toContain(record(row.total_wins, row.total_losses));
    }
    expect(ctx.texts()).not.toContain(standings[6].nickname);
  });

  it('draws guests and players who left like anyone else, with no status (FR-011, FR-029)', () => {
    const standings = makeStandings(4, { status: { 1: 'left', 2: 'kicked' } });
    const texts = draw(standings).texts().join('\n');

    for (const row of standings) {
      expect(texts).toContain(row.nickname);
    }
    expect(texts).not.toMatch(/left|kicked|離團|移出/);
  });
});

describe('renderLeaderboardCard — me and medals (041 FR-009, FR-010)', () => {
  it('tags my row with text, and nobody else’s', () => {
    const standings = makeStandings(8, { selfAt: 1 });
    const ctx = draw(standings);

    expect(ctx.texts().filter((t) => t === 'selfTag()').length).toBe(1);
    const tag = ctx.findText('selfTag()')!;
    const me = ctx.findText(standings[1].nickname)!;
    const next = ctx.findText(standings[2].nickname)!;
    // Same row as my name, well above the next player's.
    expect(Math.abs(tag.y - me.y)).toBeLessThan(30);
    expect(tag.y).toBeLessThan(next.y - 60);
  });

  it('gives ranks 1–3 a medal with the number written in it', () => {
    const ctx = draw(makeStandings(8));

    expect(ctx.recordedArcs.map((a) => a.color)).toEqual([
      MEDAL_COLORS[1],
      MEDAL_COLORS[2],
      MEDAL_COLORS[3],
    ]);
    for (const [i, arc] of ctx.recordedArcs.entries()) {
      const number = ctx.recordedTexts.find((t) => t.text === String(i + 1))!;
      expect(number.textAlign).toBe('center');
      expect(Math.abs(number.x - arc.x)).toBeLessThan(1);
    }
  });

  it('gives a medal by rank: a tied third place in row four gets one too', () => {
    const ctx = draw(makeStandings(6, { ranks: [1, 2, 3, 3, 5, 6] }));

    expect(ctx.recordedArcs.length).toBe(4);
    expect(ctx.recordedArcs[3].color).toBe(MEDAL_COLORS[3]);
  });

  it('adds my row below a divider when I am not in the top six', () => {
    const standings = makeStandings(12, { selfAt: 9 });
    const ctx = draw(standings);

    const divider = ctx.findText('⋯')!;
    const sixth = ctx.findText(standings[5].nickname)!;
    const me = ctx.findText(standings[9].nickname)!;
    expect(divider.y).toBeGreaterThan(sixth.y);
    expect(me.y).toBeGreaterThan(divider.y);
    expect(ctx.texts()).toContain('10');
    expect(ctx.texts()).toContain('selfTag()');
  });

  it('draws no divider when my row is already shown', () => {
    expect(draw(makeStandings(8, { selfAt: 3 })).findText('⋯')).toBeUndefined();
  });
});

describe('renderLeaderboardCard — few players, long names (041 Edge Cases, SC-005)', () => {
  it('draws one row for one player — no empty places', () => {
    const ctx = draw(makeStandings(1));

    expect(ctx.recordedArcs.length).toBe(1);
    expect(ctx.recordedRoundRects).toEqual([]);
    expect(ctx.texts().filter((t) => t.includes(' 勝 ')).length).toBe(1);
  });

  it('draws my row’s highlight and tag as the only rounded shapes', () => {
    const ctx = draw(makeStandings(3, { selfAt: 2 }));

    // One panel behind my row, one pill for the tag.
    expect(ctx.recordedRoundRects.length).toBe(2);
  });

  it('truncates 20-character names and a 40-character group name inside the margins', () => {
    const long = '超級無敵長的暱稱超級無敵長的暱稱測試用'.slice(0, 20);
    const standings = makeStandings(7, { selfAt: 0 }).map((row) => ({ ...row, nickname: long }));
    const ctx = draw(standings, { groupName: '這是一個名字非常非常非常非常非常非常非常非常非常非常非常非常長的羽球團' });

    const names = ctx.recordedTexts.filter((t) => t.text.startsWith('超級'));
    expect(names.length).toBe(6);
    for (const name of names) {
      expect(name.text.endsWith('…')).toBe(true);
    }
    expect(ctx.findText('這是一個')!.text.endsWith('…')).toBe(true);
    for (const text of ctx.recordedTexts) {
      const { left, right } = RecordingContext.span(text);
      expect(left, text.text).toBeGreaterThanOrEqual(SHARE_CARD_PADDING - 0.5);
      expect(right, text.text).toBeLessThanOrEqual(SHARE_CARD_WIDTH - SHARE_CARD_PADDING + 0.5);
    }
  });

  it('keeps names clear of the record column, which never moves', () => {
    const long = '超級無敵長的暱稱超級無敵長的暱稱測試用'.slice(0, 20);
    const standings = makeStandings(6, { selfAt: 4 }).map((row, i) =>
      i % 2 === 0 ? { ...row, nickname: long } : row,
    );
    const ctx = draw(standings);

    const records = ctx.recordedTexts.filter((t) => t.text.includes(' 勝 '));
    expect(new Set(records.map((r) => RecordingContext.span(r).right)).size).toBe(1);
    const recordLeft = Math.min(...records.map((r) => RecordingContext.span(r).left));
    for (const name of ctx.recordedTexts.filter((t) => t.text.startsWith('超級'))) {
      expect(RecordingContext.span(name).right).toBeLessThan(recordLeft);
    }
  });
});

describe('renderLeaderboardCard — layout (041 contracts/share-card-core.md §6)', () => {
  it('keeps the fullest card — six rows and my own — above the footer', () => {
    const ctx = draw(makeStandings(12, { selfAt: 10 }));

    expect(middleBottom(ctx)).toBeLessThanOrEqual(SHARE_CARD_MIDDLE_BOTTOM);
  });

  it('ends with the shared footer and the site address (FR-018)', () => {
    const texts = draw().texts();

    expect(texts).toContain('Rally Stats');
    expect(texts).toContain('rallystats.test');
  });

  it('keeps every row its full height in the fullest card — only the gaps may narrow', () => {
    const standings = makeStandings(12, { selfAt: 10 });
    const ctx = draw(standings);

    const y = (i: number) => ctx.findText(standings[i].nickname)!.y;
    // Podium rows are 120 apart; the name font steps from 44px to 36px
    // between row 3 and row 4, so compare rows of the same kind.
    expect(y(1) - y(0)).toBe(120);
    expect(y(2) - y(1)).toBe(120);
    expect(y(4) - y(3)).toBe(76);
    expect(y(5) - y(4)).toBe(76);
    expect(middleBottom(ctx)).toBeLessThanOrEqual(SHARE_CARD_MIDDLE_BOTTOM);
  });

  it('paints the chosen theme’s background first', () => {
    for (const theme of ['light', 'dark'] as const) {
      const ctx = draw(undefined, { theme });
      expect(ctx.recordedRects[0]).toEqual({
        x: 0,
        y: 0,
        w: 1080,
        h: 1350,
        color: SHARE_PALETTES[theme].background,
      });
    }
  });

  it('takes the row data from the standings only — one row per player drawn', () => {
    const standings = [makeStanding({ nickname: '獨行俠', rank: 1 })];

    expect(draw(standings).texts()).toContain('獨行俠');
  });
});
