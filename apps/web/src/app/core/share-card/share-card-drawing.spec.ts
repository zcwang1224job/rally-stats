import { panel, pill, truncateToWidth } from './share-card-drawing';
import { RecordingContext } from './testing/recording-context';

function ctxAt(font = '10px sans-serif'): RecordingContext {
  const ctx = new RecordingContext();
  ctx.font = font;
  return ctx;
}

describe('truncateToWidth (moved from 040)', () => {
  it('returns the text untouched when it fits', () => {
    expect(truncateToWidth(ctxAt(), 'abc', 100)).toBe('abc');
  });

  it('cuts the longest prefix that still fits with the ellipsis', () => {
    const ctx = ctxAt();

    const result = truncateToWidth(ctx, '一二三四五六', 35);
    expect(result).toBe('一二…');
    expect(ctx.measureText(result).width).toBeLessThanOrEqual(35);
  });

  it('never splits an emoji or other surrogate pair', () => {
    const ctx = ctxAt();

    const result = truncateToWidth(ctx, '🏸🏸🏸🏸🏸🏸', 20);
    expect(result.endsWith('…')).toBe(true);
    for (const char of result.slice(0, -1)) {
      expect(char).toBe('🏸');
    }
  });

  it('gives just the ellipsis when not even one character fits', () => {
    expect(truncateToWidth(ctxAt(), '一二三', 3)).toBe('…');
  });
});

describe('panel and pill', () => {
  it('fill a rounded rectangle in the given color', () => {
    const ctx = ctxAt();

    panel(ctx, 10, 20, 300, 100, '#abcdef');
    pill(ctx, 10, 200, 120, 40, '#123456');

    expect(ctx.recordedRoundRects).toEqual([
      { x: 10, y: 20, w: 300, h: 100, color: '#abcdef' },
      { x: 10, y: 200, w: 120, h: 40, color: '#123456' },
    ]);
    expect(ctx.fillCount).toBe(2);
  });
});
