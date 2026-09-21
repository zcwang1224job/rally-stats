import { formatDate } from '@angular/common';
import { SHARE_CARD_PADDING, SHARE_CARD_WIDTH, ShareCardText } from '../share-card/share-card-canvas';
import { SHARE_CARD_MIDDLE_BOTTOM } from '../share-card/share-card-layout';
import { ShareCardRenderEnv } from '../share-card/share-card-option';
import { SHARE_PALETTES } from '../share-card/share-card-palette';
import { footerOpCount, testFooter } from '../share-card/testing/footer-ops';
import { RecordingContext } from '../share-card/testing/recording-context';
import { MyStatsCardModel } from './group-share-card.models';
import { buildMyStatsCardModel } from './my-stats-card-model';
import { renderMyStatsCard } from './my-stats-card-renderer';
import { CREATED_AT, makeHistory, makeOpponents, makeRounds, makeStandings } from './testing/history-fixtures';

const ZH_DATE = 'yyyy/M/d';

/** Real-length wording for the record lines; `name(param,…)` otherwise. */
const fakeText: ShareCardText = (key, params) => {
  if (key === 'shareCard.dateFormat') {
    return ZH_DATE;
  }
  if (key === 'shareCard.brand') {
    return 'Rally Stats';
  }
  if (key === 'groupShareCard.myStats.opponentRecord') {
    return `${params?.['wins']} 勝 ${params?.['losses']} 敗`;
  }
  return `${key.split('.').pop()}(${Object.values(params ?? {}).join(',')})`;
};

function env(theme: 'light' | 'dark' = 'light'): ShareCardRenderEnv {
  return {
    palette: SHARE_PALETTES[theme],
    text: fakeText,
    fonts: { base: 'sans-serif', score: 'monospace' },
    footer: testFooter(),
  };
}

function model(overrides: Partial<MyStatsCardModel> = {}): MyStatsCardModel {
  return { ...buildMyStatsCardModel(makeHistory(), { createdAt: CREATED_AT })!, ...overrides };
}

function draw(m = model(), theme: 'light' | 'dark' = 'light'): RecordingContext {
  const ctx = new RecordingContext();
  renderMyStatsCard(ctx, m, env(theme));
  return ctx;
}

function fontSize(font: string): number {
  return Number(/(\d+)px/.exec(font)![1]);
}

/** The trend chart's panel: the only full-width rounded shape. */
function trendPanel(ctx: RecordingContext) {
  return ctx.recordedRoundRects.find((r) => r.w === SHARE_CARD_WIDTH - SHARE_CARD_PADDING * 2);
}

describe('renderMyStatsCard — what it shows (041 US3, FR-014–FR-016)', () => {
  it('writes the group, title, date, my name, win rate, record and rank', () => {
    const m = model();
    const texts = draw(m).texts();

    expect(texts).toContain('週三羽球團');
    expect(texts.join('\n')).toContain('title()');
    expect(texts.join('\n')).toContain(formatDate(CREATED_AT, ZH_DATE, 'en-US'));
    expect(texts).toContain(m.nickname);
    expect(texts).toContain(m.winRate);
    expect(texts).toContain(`record(${m.wins},${m.losses},${m.matches})`);
    expect(texts).toContain(`standing(${m.standing!.rank},${m.standing!.playerCount})`);
  });

  it('makes the win rate the biggest thing on the card', () => {
    const ctx = draw();

    const rate = ctx.findText('60%')!;
    const others = ctx.recordedTexts.filter((t) => t !== rate);
    expect(Math.max(...others.map((t) => fontSize(t.font)))).toBeLessThan(fontSize(rate.font));
  });

  it('draws the round trend as one line with a point per round', () => {
    const ctx = draw();

    expect(ctx.texts()).toContain('trendTitle()');
    expect(ctx.recordedPolylines).toEqual([{ color: SHARE_PALETTES.light.trendA, points: 3 }]);
  });

  it('lists the most-played opponents with their record against me', () => {
    const m = model();
    const texts = draw(m).texts();

    expect(texts).toContain('opponentsTitle()');
    for (const opponent of m.opponents) {
      expect(texts).toContain(opponent.nickname);
      expect(texts).toContain(`${opponent.wins} 勝 ${opponent.losses} 敗`);
    }
  });
});

describe('renderMyStatsCard — what it leaves out (041 FR-017)', () => {
  it('leaves out my rank, and its pill, when it is unknown', () => {
    const ctx = draw(model({ standing: null }));

    expect(ctx.texts().some((t) => t.startsWith('standing('))).toBe(false);
    expect(ctx.recordedRoundRects.length).toBe(1); // just the trend panel
  });

  it('leaves out the trend, and its panel, when there is none', () => {
    const ctx = draw(model({ trend: null }));

    expect(ctx.texts()).not.toContain('trendTitle()');
    expect(ctx.recordedPolylines).toEqual([]);
    expect(trendPanel(ctx)).toBeUndefined();
  });

  it('leaves out the opponents block when there are none', () => {
    expect(draw(model({ opponents: [] })).texts()).not.toContain('opponentsTitle()');
  });

  it('leaves out my name and the date when unknown', () => {
    const myName = model().nickname!;
    const texts = draw(model({ nickname: null, date: null })).texts().join('\n');

    expect(myName.length).toBeGreaterThan(0);
    expect(texts).not.toContain(myName);
    expect(texts).not.toMatch(/\d{4}\/\d{1,2}\/\d{1,2}/);
  });
});

describe('renderMyStatsCard — layout (041 SC-005, contracts/group-share-card.md §2)', () => {
  function middleBottom(ctx: RecordingContext): number {
    const e = env();
    return ctx.bottomEdge({ skipFirst: 1, skipLast: footerOpCount(e.footer, e) });
  }

  it('shrinks the trend to fit the fullest card above the footer', () => {
    const ctx = draw();

    const panel = trendPanel(ctx)!;
    // Trend block 220 with its 44px title; shrunk, but not below 140.
    expect(panel.h + 44).toBeLessThan(220);
    expect(panel.h + 44).toBeGreaterThanOrEqual(140);
    expect(middleBottom(ctx)).toBeLessThanOrEqual(SHARE_CARD_MIDDLE_BOTTOM);
  });

  it('keeps the trend full height when there is room', () => {
    const history = makeHistory({
      my_stats: { ...makeHistory().my_stats, opponent_records: makeOpponents(1) },
    });
    const ctx = draw(buildMyStatsCardModel(history, { createdAt: CREATED_AT })!);

    expect(trendPanel(ctx)!.h + 44).toBe(220);
  });

  it('truncates 20-character names — mine and opponents’ — inside the margins', () => {
    const long = '超級無敵長的暱稱超級無敵長的暱稱測試用'.slice(0, 20);
    const standings = makeStandings(4, { selfAt: 0 }).map((row) => ({ ...row, nickname: long }));
    const opponents = makeOpponents(3).map((o) => ({ ...o, nickname: long }));
    const history = makeHistory({
      final_standings: standings,
      my_stats: { ...makeHistory().my_stats, opponent_records: opponents, round_win_rates: makeRounds([0.5, 1]) },
    });
    const ctx = draw(buildMyStatsCardModel(history, { createdAt: CREATED_AT })!);

    const names = ctx.recordedTexts.filter((t) => t.text.startsWith('超級'));
    expect(names.length).toBe(4);
    for (const text of ctx.recordedTexts) {
      const { left, right } = RecordingContext.span(text);
      expect(left, text.text).toBeGreaterThanOrEqual(SHARE_CARD_PADDING - 0.5);
      expect(right, text.text).toBeLessThanOrEqual(SHARE_CARD_WIDTH - SHARE_CARD_PADDING + 0.5);
    }
    const records = ctx.recordedTexts.filter((t) => t.text.includes(' 勝 '));
    const recordLeft = Math.min(...records.map((r) => RecordingContext.span(r).left));
    for (const name of names.slice(1)) {
      expect(RecordingContext.span(name).right).toBeLessThan(recordLeft);
    }
  });

  it('ends with the shared footer (FR-018)', () => {
    const texts = draw().texts();

    expect(texts).toContain('Rally Stats');
    expect(texts).toContain('rallystats.test');
  });

  it('paints the chosen theme’s background first', () => {
    for (const theme of ['light', 'dark'] as const) {
      expect(draw(model(), theme).recordedRects[0].color).toBe(SHARE_PALETTES[theme].background);
    }
  });
});
