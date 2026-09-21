import { SHARE_CARD_PADDING, SHARE_CARD_WIDTH, ShareCardText } from './share-card-canvas';
import { drawPromoFooter } from './share-card-footer';
import { SHARE_CARD_FOOTER_TOP } from './share-card-layout';
import { SHARE_PALETTES } from './share-card-palette';
import { testFooter } from './testing/footer-ops';
import { RecordingContext } from './testing/recording-context';

const FONTS = { base: 'sans-serif', score: 'monospace' };
const text: ShareCardText = (key) => (key === 'shareCard.brand' ? 'Rally Stats' : key);
const env = { palette: SHARE_PALETTES.light, text, fonts: FONTS };

function draw(meta: string | null): RecordingContext {
  const ctx = new RecordingContext();
  drawPromoFooter(ctx, testFooter({ meta }), env);
  return ctx;
}

describe('drawPromoFooter — the footer 040 cards already have (041 Phase 2)', () => {
  it('draws a divider above the footer and the brand on the right', () => {
    const ctx = draw(null);

    const divider = ctx.recordedRects.find((r) => r.color === SHARE_PALETTES.light.divider)!;
    expect(divider.y).toBeLessThan(SHARE_CARD_FOOTER_TOP);
    expect(divider.w).toBe(SHARE_CARD_WIDTH - SHARE_CARD_PADDING * 2);

    const brand = ctx.findText('Rally Stats')!;
    expect(brand.textAlign).toBe('right');
    expect(brand.x).toBe(SHARE_CARD_WIDTH - SHARE_CARD_PADDING);
  });

  it('writes the meta line on the left, clear of the brand', () => {
    const ctx = draw('比賽時長 18 分 32 秒 · 平均每分 29 秒');

    const meta = ctx.findText('比賽時長')!;
    const brand = ctx.findText('Rally Stats')!;
    expect(meta.x).toBe(SHARE_CARD_PADDING);
    expect(RecordingContext.span(meta).right).toBeLessThan(RecordingContext.span(brand).left);
  });

  it('leaves the meta line out when there is none', () => {
    expect(draw(null).texts()).toEqual(['Rally Stats']);
  });

  it('does not draw the link or a QR code yet', () => {
    const ctx = draw(null);

    expect(ctx.texts().join('\n')).not.toContain('rallystats.test');
    expect(ctx.recordedRoundRects).toEqual([]);
  });
});
