import { SHARE_CARD_HEIGHT, ShareCardText } from './share-card-canvas';
import { drawPromoFooter } from './share-card-footer';
import { SHARE_CARD_FOOTER_TOP } from './share-card-layout';
import { QrMatrix } from './share-card-option';
import { SHARE_PALETTES } from './share-card-palette';
import { qrLayout } from './share-card-qr';
import { testFooter } from './testing/footer-ops';
import { RecordingContext } from './testing/recording-context';

const FONTS = { base: 'sans-serif', score: 'monospace' };
const TEXT: Record<string, string> = {
  'shareCard.brand': 'Rally Stats',
  'shareCard.tagline': '計分・排點・戰績，打球一站搞定',
  'shareCard.scanHint': '掃描 QR 碼開始使用',
};
const text: ShareCardText = (key) => TEXT[key] ?? key;

/** A checkerboard QR matrix of the given size. */
function matrix(size: number): QrMatrix {
  return { size, isDark: (row, col) => (row + col) % 2 === 0 };
}

function darkCount(qr: QrMatrix): number {
  let count = 0;
  for (let row = 0; row < qr.size; row++) {
    for (let col = 0; col < qr.size; col++) {
      count += qr.isDark(row, col) ? 1 : 0;
    }
  }
  return count;
}

const PLATE = { x: 768, y: 1054, size: 240 };
const LEFT_LIMIT = PLATE.x - 24;

function draw(
  options: { qr?: QrMatrix | null; meta?: string | null; theme?: 'light' | 'dark'; tagline?: string; url?: string } = {},
): RecordingContext {
  const ctx = new RecordingContext();
  const footer = testFooter({
    qr: options.qr === undefined ? matrix(33) : options.qr,
    meta: options.meta ?? null,
    ...(options.url ? { link: { qrUrl: 'https://x/?ref=card-rank', displayUrl: options.url } } : {}),
  });
  const localText: ShareCardText = (key) =>
    key === 'shareCard.tagline' && options.tagline ? options.tagline : text(key);
  drawPromoFooter(ctx, footer, {
    palette: SHARE_PALETTES[options.theme ?? 'light'],
    text: localText,
    fonts: FONTS,
  });
  return ctx;
}

describe('drawPromoFooter — the QR code (041 FR-018, FR-020)', () => {
  for (const theme of ['light', 'dark'] as const) {
    it(`sits on a white 240×240 plate with near-black modules in ${theme} (never inverted)`, () => {
      const qr = matrix(33);
      const ctx = draw({ qr, theme });

      expect(ctx.recordedRoundRects).toEqual([
        { x: PLATE.x, y: PLATE.y, w: 240, h: 240, color: '#ffffff' },
      ]);
      const modules = ctx.recordedRects.filter((r) => r.color === '#111827');
      const { modulePx } = qrLayout(33)!;
      expect(modules.length).toBe(darkCount(qr));
      for (const m of modules) {
        expect([m.w, m.h]).toEqual([modulePx, modulePx]);
        expect(m.x).toBeGreaterThanOrEqual(PLATE.x);
        expect(m.y).toBeGreaterThanOrEqual(PLATE.y);
        expect(m.x + m.w).toBeLessThanOrEqual(PLATE.x + PLATE.size);
        expect(m.y + m.h).toBeLessThanOrEqual(PLATE.y + PLATE.size);
      }
    });
  }

  it('leaves the code out, but keeps the address, when there is no matrix', () => {
    const ctx = draw({ qr: null });

    expect(ctx.recordedRoundRects).toEqual([]);
    expect(ctx.recordedRects.filter((r) => r.color === '#111827')).toEqual([]);
    expect(ctx.texts()).toContain('rallystats.test');
    expect(ctx.texts()).not.toContain('掃描 QR 碼開始使用');
  });

  it('leaves the code out when the link is too long to draw it scannably', () => {
    const ctx = draw({ qr: matrix(61) });

    expect(ctx.recordedRoundRects).toEqual([]);
    expect(ctx.texts()).not.toContain('掃描 QR 碼開始使用');
  });
});

describe('drawPromoFooter — the words (041 FR-018, contracts §5)', () => {
  it('writes meta, brand, tagline, address and scan hint, top to bottom, on the left', () => {
    const ctx = draw({ meta: '比賽時長 18 分 32 秒' });

    const lines = ['比賽時長 18 分 32 秒', 'Rally Stats', '計分・排點・戰績，打球一站搞定', 'rallystats.test', '掃描 QR 碼開始使用'];
    const drawn = lines.map((line) => ctx.findText(line)!);
    expect(drawn.every(Boolean)).toBe(true);
    for (let i = 1; i < drawn.length; i++) {
      expect(drawn[i].y).toBeGreaterThan(drawn[i - 1].y);
    }
    for (const line of drawn) {
      expect(line.x).toBe(72);
      expect(RecordingContext.span(line).right).toBeLessThanOrEqual(LEFT_LIMIT);
    }
  });

  it('closes the gap when there is no meta line', () => {
    const withMeta = draw({ meta: 'meta' }).findText('Rally Stats')!;
    const without = draw({ meta: null }).findText('Rally Stats')!;

    expect(without.y).toBe(SHARE_CARD_FOOTER_TOP);
    expect(withMeta.y).toBeGreaterThan(without.y);
  });

  it('keeps a long tagline and address clear of the QR plate', () => {
    const ctx = draw({ tagline: '很長'.repeat(100), url: 'a-very-long-host-name.'.repeat(4) + 'example' });

    for (const t of ctx.recordedTexts) {
      expect(RecordingContext.span(t).right, t.text).toBeLessThanOrEqual(LEFT_LIMIT);
    }
    expect(ctx.findText('很長')!.text.endsWith('…')).toBe(true);
  });

  it('uses the full width for the words when there is no code', () => {
    const ctx = draw({ qr: null, tagline: '很長'.repeat(100) });

    const tagline = ctx.findText('很長')!;
    expect(RecordingContext.span(tagline).right).toBeGreaterThan(LEFT_LIMIT);
    expect(RecordingContext.span(tagline).right).toBeLessThanOrEqual(1008);
  });

  it('stays between the divider and the bottom margin', () => {
    const ctx = draw({ meta: 'meta' });

    const divider = ctx.recordedRects.find((r) => r.color === SHARE_PALETTES.light.divider)!;
    expect(divider.y).toBe(1026);
    for (const op of ctx.ops) {
      expect(op.top).toBeGreaterThanOrEqual(1026);
      expect(op.bottom).toBeLessThanOrEqual(SHARE_CARD_HEIGHT - 56);
    }
  });
});
