import { SHARE_CARD_PADDING, SHARE_CARD_WIDTH, ShareCardCanvas } from './share-card-canvas';
import { truncateToWidth } from './share-card-drawing';
import { SHARE_CARD_FOOTER_TOP } from './share-card-layout';
import { PromoFooter, ShareCardRenderEnv } from './share-card-option';

const CONTENT_WIDTH = SHARE_CARD_WIDTH - SHARE_CARD_PADDING * 2;
const RIGHT_EDGE = SHARE_CARD_WIDTH - SHARE_CARD_PADDING;

/** 041-group-share-cards: the footer every card ends with. For now it is
 * 040's footer moved as-is — the brand on the right, the optional meta
 * line (the match card's duration and pace) on the left. */
export function drawPromoFooter(
  ctx: ShareCardCanvas,
  footer: PromoFooter,
  { palette, text, fonts }: Omit<ShareCardRenderEnv, 'footer'>,
): void {
  ctx.fillStyle = palette.divider;
  ctx.fillRect(SHARE_CARD_PADDING, SHARE_CARD_FOOTER_TOP - 32, CONTENT_WIDTH, 2);

  ctx.textAlign = 'right';
  ctx.fillStyle = palette.text;
  ctx.font = `bold 32px ${fonts.base}`;
  const brand = text('shareCard.brand');
  ctx.fillText(brand, RIGHT_EDGE, SHARE_CARD_FOOTER_TOP);
  const brandWidth = ctx.measureText(brand).width;

  if (footer.meta !== null) {
    ctx.textAlign = 'left';
    ctx.fillStyle = palette.textMuted;
    ctx.font = `28px ${fonts.base}`;
    ctx.fillText(
      truncateToWidth(ctx, footer.meta, CONTENT_WIDTH - brandWidth - 32),
      SHARE_CARD_PADDING,
      SHARE_CARD_FOOTER_TOP + 2,
    );
  }
}
