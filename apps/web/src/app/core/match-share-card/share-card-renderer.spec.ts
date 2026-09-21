import { formatDate } from '@angular/common';
import { ShareCardContext, ShareCardModel, ShareCardText } from './share-card.models';
import { buildShareCardModel } from './share-card-model';
import { SHARE_PALETTES } from './share-card-palette';
import {
  SHARE_CARD_HEIGHT,
  SHARE_CARD_PADDING,
  SHARE_CARD_WIDTH,
  renderShareCard,
  truncateToWidth,
} from './share-card-renderer';
import {
  makeDetail,
  makePartial,
  makeSingles,
  withMomentum,
  withTempo,
} from './testing/detail-fixtures';
import { RecordingContext } from './testing/recording-context';

const neutral: ShareCardContext = { groupName: '週三羽球團', perspective: { kind: 'neutral' } };
const FONTS = { base: 'sans-serif', score: 'monospace' };
const ZH_DATE = 'yyyy/M/d';
const EN_DATE = 'MMM d, yyyy';

/** Returns the real date pattern (the renderer hands it to formatDate), the
 * real brand, and a short `name(param,…)` for everything else — short like
 * real wording, so it isn't truncated, yet still shows what was asked. */
function fakeText(dateFormat = ZH_DATE): ShareCardText {
  return (key, params) => {
    if (key === 'matchShareCard.dateFormat') {
      return dateFormat;
    }
    if (key === 'matchShareCard.brand') {
      return 'Rally Stats';
    }
    const name = key.replace('matchShareCard.', '');
    return `${name}(${Object.values(params ?? {}).join(',')})`;
  };
}

function draw(model: ShareCardModel, dateFormat = ZH_DATE): RecordingContext {
  const ctx = new RecordingContext();
  renderShareCard(ctx, model, SHARE_PALETTES.light, fakeText(dateFormat), FONTS);
  return ctx;
}

describe('renderShareCard — basic card (040 US1)', () => {
  it('paints the whole 1080×1350 canvas with the theme background first', () => {
    const ctx = draw(buildShareCardModel(makeDetail(), neutral));

    expect(SHARE_CARD_WIDTH).toBe(1080);
    expect(SHARE_CARD_HEIGHT).toBe(1350);
    expect(ctx.recordedRects[0]).toEqual({
      x: 0,
      y: 0,
      w: 1080,
      h: 1350,
      color: SHARE_PALETTES.light.background,
    });
  });

  it('draws the group, date, round, every name, both scores, the badge and the brand', () => {
    const detail = makeDetail();
    const ctx = draw(buildShareCardModel(detail, neutral));
    const texts = ctx.texts().join('\n');

    expect(texts).toContain('週三羽球團');
    expect(texts).toContain(formatDate(detail.started_at!, ZH_DATE, 'en-US'));
    expect(texts).toContain('round(3)');
    for (const name of ['王小明', '陳大華', '林小美', '張阿強']) {
      expect(texts).toContain(name);
    }
    expect(ctx.texts()).toContain('21');
    expect(ctx.texts()).toContain('17');
    expect(texts).toContain('badge.win()');
    expect(texts).toContain('Rally Stats');
  });

  it('formats the date with the English pattern too, without Chinese locale data (U1)', () => {
    const detail = makeDetail();

    expect(() => draw(buildShareCardModel(detail, neutral), ZH_DATE)).not.toThrow();
    const en = draw(buildShareCardModel(detail, neutral), EN_DATE);
    expect(en.texts().join('\n')).toContain(formatDate(detail.started_at!, EN_DATE, 'en-US'));
  });

  it('keeps every piece of text inside the side margins', () => {
    const ctx = draw(buildShareCardModel(makeDetail(), neutral));

    for (const text of ctx.recordedTexts) {
      const { left, right } = RecordingContext.span(text);
      expect(left, text.text).toBeGreaterThanOrEqual(SHARE_CARD_PADDING - 0.5);
      expect(right, text.text).toBeLessThanOrEqual(SHARE_CARD_WIDTH - SHARE_CARD_PADDING + 0.5);
    }
  });

  it('truncates a 20-character doubles name with an ellipsis, clear of the score (SC-005)', () => {
    const longName = '超級無敵長的暱稱超級無敵長的暱稱測試用'.slice(0, 20);
    const ctx = draw(
      buildShareCardModel(
        makeDetail({
          team_a: [
            { roster_entry_id: 'a1', nickname: longName, team: 'A' },
            { roster_entry_id: 'a2', nickname: longName, team: 'A' },
          ],
        }),
        neutral,
      ),
    );

    const names = ctx.recordedTexts.filter((t) => t.text.startsWith('超級'));
    expect(names.length).toBe(2);
    const score = ctx.recordedTexts.find((t) => t.text === '21')!;
    for (const name of names) {
      expect(name.text.endsWith('…')).toBe(true);
      expect(RecordingContext.span(name).right).toBeLessThan(RecordingContext.span(score).left);
    }
  });

  it('never draws a link or QR code (FR-006)', () => {
    const texts = draw(buildShareCardModel(makeDetail(), neutral)).texts().join('\n');

    expect(texts).not.toMatch(/http|www|:\/\//);
  });

  it('shows the duration, and leaves it out when there is none', () => {
    const withDuration = draw(buildShareCardModel(makeDetail(), neutral)).texts().join('\n');
    expect(withDuration).toContain('duration(18,32)');

    const without = draw(buildShareCardModel(makeDetail({ ended_at: null }), neutral));
    expect(without.texts().join('\n')).not.toContain('duration(');
  });

  it('switches to hours for a match over an hour long', () => {
    const texts = draw(
      buildShareCardModel(
        makeDetail({ started_at: '2026-09-21T10:00:00Z', ended_at: '2026-09-21T11:05:00Z' }),
        neutral,
      ),
    )
      .texts()
      .join('\n');

    expect(texts).toContain('durationHours(1,5)');
  });
});

describe('renderShareCard — trend, highlights, pace (040 US2)', () => {
  const rich = () =>
    makeDetail({
      score_a: 21,
      score_b: 10,
      momentum_stats: withMomentum(6, 0, 3),
      tempo_stats: withTempo(29.4),
    });

  it('draws one line per team with a point for every trend point', () => {
    const model = buildShareCardModel(rich(), neutral);
    const ctx = draw(model);

    expect(ctx.recordedPolylines.map((p) => p.points)).toEqual([
      model.trend!.length,
      model.trend!.length,
    ]);
    expect(ctx.recordedPolylines.map((p) => p.color)).toEqual([
      SHARE_PALETTES.light.trendA,
      SHARE_PALETTES.light.trendB,
    ]);
  });

  it('writes each highlight with its own numbers', () => {
    const texts = draw(buildShareCardModel(rich(), neutral)).texts().join('\n');

    expect(texts).toContain('highlight.run(6)');
    expect(texts).toContain('highlight.leadChanges(3)');
    expect(texts).toContain('highlight.bigMargin(11)');
  });

  it('adds the average per point to the footer', () => {
    const texts = draw(buildShareCardModel(rich(), neutral)).texts().join('\n');

    expect(texts).toContain('duration(18,32) · avgPerPoint(29)');
  });

  it('leaves no trace of trend, highlights or pace for a partial record (FR-009)', () => {
    const ctx = draw(buildShareCardModel(makePartial({ momentum_stats: withMomentum(6, 0, 3) }), neutral));

    expect(ctx.recordedPolylines).toEqual([]);
    expect(ctx.texts().join('\n')).not.toMatch(/highlight\.|avgPerPoint/);
    // No empty panel left where they would have been.
    expect(ctx.recordedRects.filter((r) => r.color === SHARE_PALETTES.light.panel)).toEqual([]);
    expect(ctx.recordedRoundRects.length).toBe(1); // just the WIN badge
  });

  it('keeps the richest card inside the margins too', () => {
    const ctx = draw(buildShareCardModel(rich(), neutral));

    for (const text of ctx.recordedTexts) {
      const { left, right } = RecordingContext.span(text);
      expect(left, text.text).toBeGreaterThanOrEqual(SHARE_CARD_PADDING - 0.5);
      expect(right, text.text).toBeLessThanOrEqual(SHARE_CARD_WIDTH - SHARE_CARD_PADDING + 0.5);
      expect(text.y, text.text).toBeLessThan(SHARE_CARD_HEIGHT - SHARE_CARD_PADDING);
    }
  });
});

describe('renderShareCard — my perspective (040 US3)', () => {
  const mine = (myTeam: 'A' | 'B'): ShareCardContext => ({
    groupName: '週三羽球團',
    perspective: { kind: 'mine', myTeam },
  });

  it('writes Victory or Defeat as text, not just a color (FR-029)', () => {
    const won = draw(buildShareCardModel(makeDetail(), mine('A'))).texts();
    const lost = draw(buildShareCardModel(makeDetail(), mine('B'))).texts();

    expect(won).toContain('badge.victory()');
    expect(lost).toContain('badge.defeat()');
    expect(lost).not.toContain('badge.win()');
  });

  it('sets my team apart with a panel behind it, drawn before its names', () => {
    const ctx = draw(buildShareCardModel(makeSingles(), mine('B')));
    const neutralCtx = draw(buildShareCardModel(makeSingles(), neutral));

    // mine: the emphasis panel plus the badge; neutral: just the badge.
    expect(ctx.recordedRoundRects.length).toBe(neutralCtx.recordedRoundRects.length + 1);
    const panel = ctx.recordedRoundRects[0];
    const myName = ctx.findText('林小美')!;
    expect(myName.y).toBeGreaterThan(panel.y);
    expect(myName.y).toBeLessThan(panel.y + panel.h);
    const opponent = ctx.findText('王小明')!;
    expect(opponent.y).toBeGreaterThan(panel.y + panel.h);
  });
});

describe('truncateToWidth', () => {
  it('returns the text untouched when it fits', () => {
    const ctx = new RecordingContext();
    ctx.font = '10px sans-serif';

    expect(truncateToWidth(ctx, 'abc', 100)).toBe('abc');
  });

  it('cuts the longest prefix that still fits with the ellipsis', () => {
    const ctx = new RecordingContext();
    ctx.font = '10px sans-serif';

    const result = truncateToWidth(ctx, '一二三四五六', 35);
    expect(result).toBe('一二…');
    expect(ctx.measureText(result).width).toBeLessThanOrEqual(35);
  });
});
