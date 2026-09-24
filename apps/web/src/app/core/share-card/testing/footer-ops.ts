import { drawPromoFooter } from '../share-card-footer';
import { PromoFooter, ShareCardRenderEnv } from '../share-card-option';
import { RecordingContext } from './recording-context';

/** A fixed footer for renderer tests: a test host, no QR, no meta line. */
export function testFooter(overrides: Partial<PromoFooter> = {}): PromoFooter {
  return {
    link: { qrUrl: 'https://rallystats.test/?ref=card-match', displayUrl: 'rallystats.test' },
    qr: null,
    meta: null,
    ...overrides,
  };
}

/** How many marks the footer draws — every card draws its footer last, so
 * `ctx.bottomEdge({ skipFirst: 1, skipLast: footerOpCount(…) })` measures
 * just the middle of a card (after the background, before the footer). */
export function footerOpCount(footer: PromoFooter, env: Omit<ShareCardRenderEnv, 'footer'>): number {
  const ctx = new RecordingContext();
  drawPromoFooter(ctx, footer, env);
  return ctx.opCount();
}
