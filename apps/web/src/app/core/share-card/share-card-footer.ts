import { SHARE_CARD_PADDING, SHARE_CARD_WIDTH, ShareCardCanvas } from './share-card-canvas';
import { roundedFill, truncateToWidth } from './share-card-drawing';
import { SHARE_CARD_FOOTER_TOP } from './share-card-layout';
import { PromoFooter, ShareCardRenderEnv } from './share-card-option';
import { QR_PLATE_SIZE, qrLayout } from './share-card-qr';

const CONTENT_WIDTH = SHARE_CARD_WIDTH - SHARE_CARD_PADDING * 2;
const RIGHT_EDGE = SHARE_CARD_WIDTH - SHARE_CARD_PADDING;
const DIVIDER_Y = SHARE_CARD_FOOTER_TOP - 28;
const PLATE_X = RIGHT_EDGE - QR_PLATE_SIZE;
const TEXT_GAP = 24;

interface Line {
  text: string;
  font: string;
  color: string;
  /** Room the line takes, top to next line. */
  height: number;
}

/** 041-group-share-cards US2 (FR-018, contracts/share-card-core.md §5): the
 * footer every card ends with — what turns a shared picture into a way in.
 * On the right, a QR code of the card's link on a white plate; on the left,
 * the optional meta line, the brand, the tagline, the site address (short
 * enough to type) and a hint to scan. With no code, the words take the full
 * width and the hint goes. */
export function drawPromoFooter(
  ctx: ShareCardCanvas,
  footer: PromoFooter,
  { palette, text, fonts }: Omit<ShareCardRenderEnv, 'footer'>,
): void {
  ctx.textBaseline = 'top';
  ctx.fillStyle = palette.divider;
  ctx.fillRect(SHARE_CARD_PADDING, DIVIDER_Y, CONTENT_WIDTH, 2);

  const layout = footer.qr ? qrLayout(footer.qr.size) : null;
  if (footer.qr && layout) {
    roundedFill(ctx, PLATE_X, SHARE_CARD_FOOTER_TOP, QR_PLATE_SIZE, QR_PLATE_SIZE, 16, palette.qrPlate);
    ctx.fillStyle = palette.qrModule;
    const left = PLATE_X + layout.offset;
    const top = SHARE_CARD_FOOTER_TOP + layout.offset;
    for (let row = 0; row < footer.qr.size; row++) {
      for (let col = 0; col < footer.qr.size; col++) {
        if (footer.qr.isDark(row, col)) {
          ctx.fillRect(left + col * layout.modulePx, top + row * layout.modulePx, layout.modulePx, layout.modulePx);
        }
      }
    }
  }

  const hasCode = layout !== null;
  const maxWidth = (hasCode ? PLATE_X - TEXT_GAP : RIGHT_EDGE) - SHARE_CARD_PADDING;
  const lines: Line[] = [];
  if (footer.meta !== null) {
    lines.push({ text: footer.meta, font: `26px ${fonts.base}`, color: palette.textMuted, height: 40 });
  }
  lines.push(
    { text: text('shareCard.brand'), font: `bold 36px ${fonts.base}`, color: palette.text, height: 48 },
    { text: text('shareCard.tagline'), font: `28px ${fonts.base}`, color: palette.textMuted, height: 48 },
    { text: footer.link.displayUrl, font: `bold 32px ${fonts.base}`, color: palette.text, height: 50 },
  );
  if (hasCode) {
    lines.push({ text: text('shareCard.scanHint'), font: `24px ${fonts.base}`, color: palette.textMuted, height: 32 });
  }

  ctx.textAlign = 'left';
  let y = SHARE_CARD_FOOTER_TOP;
  for (const line of lines) {
    ctx.font = line.font;
    ctx.fillStyle = line.color;
    ctx.fillText(truncateToWidth(ctx, line.text, maxWidth), SHARE_CARD_PADDING, y);
    y += line.height;
  }
}
