import { ShareCardCanvas } from './share-card-canvas';

/** 041-group-share-cards: small drawing helpers every card uses, moved
 * unchanged from 040's renderer. */

export function panel(
  ctx: ShareCardCanvas,
  x: number,
  y: number,
  width: number,
  height: number,
  color: string,
): void {
  roundedFill(ctx, x, y, width, height, 24, color);
}

export function pill(
  ctx: ShareCardCanvas,
  x: number,
  y: number,
  width: number,
  height: number,
  color: string,
): void {
  roundedFill(ctx, x, y, width, height, height / 2, color);
}

export function roundedFill(
  ctx: ShareCardCanvas,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
  color: string,
): void {
  ctx.fillStyle = color;
  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(x, y, width, height, radius);
  } else {
    ctx.moveTo(x, y);
    ctx.lineTo(x + width, y);
    ctx.lineTo(x + width, y + height);
    ctx.lineTo(x, y + height);
  }
  ctx.fill();
}

/** The longest prefix that still fits `maxWidth` with a trailing "…" — or
 * the text itself when it already fits (SC-005: a 20-character nickname
 * must never run into the score or off the card). */
export function truncateToWidth(ctx: ShareCardCanvas, value: string, maxWidth: number): string {
  if (ctx.measureText(value).width <= maxWidth) {
    return value;
  }
  const chars = [...value];
  let low = 0;
  let high = chars.length;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (ctx.measureText(`${chars.slice(0, mid).join('')}…`).width <= maxWidth) {
      low = mid;
    } else {
      high = mid - 1;
    }
  }
  return `${chars.slice(0, low).join('')}…`;
}
