import { formatDate } from '@angular/common';
import {
  CardTeam,
  ScoreTrendPoint,
  ShareCardCanvas,
  ShareCardFonts,
  ShareCardModel,
  ShareCardText,
  SharePalette,
} from './share-card.models';

export const SHARE_CARD_WIDTH = 1080;
export const SHARE_CARD_HEIGHT = 1350;
export const SHARE_CARD_PADDING = 72;

const CONTENT_WIDTH = SHARE_CARD_WIDTH - SHARE_CARD_PADDING * 2;
const RIGHT_EDGE = SHARE_CARD_WIDTH - SHARE_CARD_PADDING;
const BLOCK_GAP = 48;

// Team rows: color bar, names, score on the right.
const NAME_INDENT = 36;
const NAME_LINE = 56;
const SCORE_SIZE = 150;
const SCORE_COLUMN = 300;
const NAME_MAX_WIDTH = CONTENT_WIDTH - NAME_INDENT - SCORE_COLUMN - 24;
const BADGE_HEIGHT = 48;
const BADGE_GAP = 16;
const TEAM_MIN_HEIGHT = 150;

const TREND_HEIGHT = 240;
const TREND_INSET = 28;
const HIGHLIGHT_LINE = 60;
const HIGHLIGHT_INSET = 24;

const FOOTER_TOP = SHARE_CARD_HEIGHT - SHARE_CARD_PADDING - 32;
const MIDDLE_TOP = 230;
const MIDDLE_BOTTOM = FOOTER_TOP - 72;

interface Block {
  height: number;
  draw(y: number): void;
}

/** 040-match-share-card: draws the 1080×1350 card (FR-004). The header is
 * pinned to the top and the footer to the bottom; the middle blocks are
 * stacked and centered between them, and a block with nothing to show is
 * simply not in the stack — no empty frame, no placeholder (FR-009).
 * Draws no link or QR code of any kind (FR-006). */
export function renderShareCard(
  ctx: ShareCardCanvas,
  model: ShareCardModel,
  palette: SharePalette,
  text: ShareCardText,
  fonts: ShareCardFonts,
): void {
  ctx.textBaseline = 'top';
  ctx.fillStyle = palette.background;
  ctx.fillRect(0, 0, SHARE_CARD_WIDTH, SHARE_CARD_HEIGHT);

  drawHeader(ctx, model, palette, text, fonts);

  const blocks: Block[] = [teamsBlock(ctx, model, palette, text, fonts)];
  if (model.trend && model.trend.length > 1) {
    blocks.push(trendBlock(ctx, model.trend, palette));
  }
  if (model.highlights.length > 0) {
    blocks.push(highlightsBlock(ctx, model, palette, text, fonts));
  }
  const total =
    blocks.reduce((sum, block) => sum + block.height, 0) + BLOCK_GAP * (blocks.length - 1);
  let y = MIDDLE_TOP + Math.max(0, (MIDDLE_BOTTOM - MIDDLE_TOP - total) / 2);
  for (const block of blocks) {
    block.draw(y);
    y += block.height + BLOCK_GAP;
  }

  drawFooter(ctx, model, palette, text, fonts);
}

function drawHeader(
  ctx: ShareCardCanvas,
  model: ShareCardModel,
  palette: SharePalette,
  text: ShareCardText,
  fonts: ShareCardFonts,
): void {
  const top = SHARE_CARD_PADDING;
  ctx.textAlign = 'left';
  ctx.fillStyle = palette.text;
  ctx.font = `bold 44px ${fonts.base}`;
  ctx.fillText(truncateToWidth(ctx, model.groupName, CONTENT_WIDTH), SHARE_CARD_PADDING, top);

  // The language decides the date pattern, never the locale: the app has
  // no zh-TW locale data registered (research.md Decision 8).
  const date = model.startedAt
    ? formatDate(model.startedAt, text('matchShareCard.dateFormat'), 'en-US')
    : null;
  const round = text('matchShareCard.round', { round: model.roundNumber });
  const meta = [date, round].filter((part): part is string => !!part).join(' · ');
  ctx.fillStyle = palette.textMuted;
  ctx.font = `30px ${fonts.base}`;
  ctx.fillText(truncateToWidth(ctx, meta, CONTENT_WIDTH), SHARE_CARD_PADDING, top + 64);
}

function teamsBlock(
  ctx: ShareCardCanvas,
  model: ShareCardModel,
  palette: SharePalette,
  text: ShareCardText,
  fonts: ShareCardFonts,
): Block {
  const heights = model.teams.map(teamHeight);
  return {
    height: heights[0] + BLOCK_GAP + heights[1],
    draw(y) {
      drawTeam(ctx, model.teams[0], y, heights[0], palette, text, fonts);
      const dividerY = y + heights[0] + BLOCK_GAP / 2;
      ctx.fillStyle = palette.divider;
      ctx.fillRect(SHARE_CARD_PADDING, dividerY - 1, CONTENT_WIDTH, 2);
      drawTeam(ctx, model.teams[1], y + heights[0] + BLOCK_GAP, heights[1], palette, text, fonts);
    },
  };
}

function teamHeight(team: CardTeam): number {
  const names = Math.max(team.nicknames.length, 1) * NAME_LINE;
  return Math.max(names + (team.badge ? BADGE_GAP + BADGE_HEIGHT : 0), TEAM_MIN_HEIGHT);
}

function drawTeam(
  ctx: ShareCardCanvas,
  team: CardTeam,
  y: number,
  height: number,
  palette: SharePalette,
  text: ShareCardText,
  fonts: ShareCardFonts,
): void {
  ctx.fillStyle = team.team === 'A' ? palette.teamA : palette.teamB;
  ctx.fillRect(SHARE_CARD_PADDING, y, 12, height);

  const nameX = SHARE_CARD_PADDING + NAME_INDENT;
  ctx.textAlign = 'left';
  ctx.fillStyle = palette.text;
  ctx.font = `${team.isWinner ? 'bold ' : ''}44px ${fonts.base}`;
  team.nicknames.forEach((name, index) => {
    ctx.fillText(truncateToWidth(ctx, name, NAME_MAX_WIDTH), nameX, y + index * NAME_LINE);
  });

  if (team.badge) {
    const muted = team.badge === 'defeat';
    const label = text(`matchShareCard.badge.${team.badge}`);
    ctx.font = `bold 28px ${fonts.base}`;
    const labelText = truncateToWidth(ctx, label, NAME_MAX_WIDTH - 40);
    const width = ctx.measureText(labelText).width + 40;
    const badgeY = y + Math.max(team.nicknames.length, 1) * NAME_LINE + BADGE_GAP;
    pill(ctx, nameX, badgeY, width, BADGE_HEIGHT, muted ? palette.badgeMutedBackground : palette.badgeBackground);
    ctx.fillStyle = muted ? palette.badgeMutedText : palette.badgeText;
    ctx.fillText(labelText, nameX + 20, badgeY + 10);
  }

  // The winner's score is bold and full-strength; the loser's stays fully
  // legible, just lighter — weight and badge carry the result, not color
  // alone (FR-029).
  ctx.textAlign = 'right';
  ctx.fillStyle = team.isWinner ? palette.text : palette.textMuted;
  ctx.font = `${team.isWinner ? 'bold' : 'normal'} ${SCORE_SIZE}px ${fonts.score}`;
  ctx.fillText(String(team.score), RIGHT_EDGE, y + (height - SCORE_SIZE) / 2);
}

/** The same points the match detail chart plots (score-trend.ts), drawn as
 * one line per team inside a rounded panel. */
function trendBlock(
  ctx: ShareCardCanvas,
  trend: ScoreTrendPoint[],
  palette: SharePalette,
): Block {
  return {
    height: TREND_HEIGHT,
    draw(y) {
      panel(ctx, SHARE_CARD_PADDING, y, CONTENT_WIDTH, TREND_HEIGHT, palette.panel);
      const left = SHARE_CARD_PADDING + TREND_INSET;
      const top = y + TREND_INSET;
      const width = CONTENT_WIDTH - TREND_INSET * 2;
      const height = TREND_HEIGHT - TREND_INSET * 2;
      const at = (point: ScoreTrendPoint, yPercent: number) => ({
        x: left + (point.x / 100) * width,
        y: top + (yPercent / 100) * height,
      });
      const lines: [string, (p: ScoreTrendPoint) => number][] = [
        [palette.trendA, (p) => p.yA],
        [palette.trendB, (p) => p.yB],
      ];
      for (const [color, yOf] of lines) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 6;
        ctx.lineJoin = 'round';
        ctx.beginPath();
        trend.forEach((point, index) => {
          const { x, y: pointY } = at(point, yOf(point));
          if (index === 0) {
            ctx.moveTo(x, pointY);
          } else {
            ctx.lineTo(x, pointY);
          }
        });
        ctx.stroke();
        const last = trend[trend.length - 1];
        const end = at(last, yOf(last));
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(end.x, end.y, 9, 0, Math.PI * 2);
        ctx.fill();
      }
    },
  };
}

function highlightsBlock(
  ctx: ShareCardCanvas,
  model: ShareCardModel,
  palette: SharePalette,
  text: ShareCardText,
  fonts: ShareCardFonts,
): Block {
  const rows = model.highlights.length;
  const height = rows * HIGHLIGHT_LINE + HIGHLIGHT_INSET * 2;
  const dotColor = model.teams[0].team === 'A' ? palette.teamA : palette.teamB;
  return {
    height,
    draw(y) {
      panel(ctx, SHARE_CARD_PADDING, y, CONTENT_WIDTH, height, palette.panel);
      const textX = SHARE_CARD_PADDING + 64;
      model.highlights.forEach((highlight, index) => {
        const rowTop = y + HIGHLIGHT_INSET + index * HIGHLIGHT_LINE;
        ctx.fillStyle = dotColor;
        ctx.beginPath();
        ctx.arc(SHARE_CARD_PADDING + 36, rowTop + HIGHLIGHT_LINE / 2, 8, 0, Math.PI * 2);
        ctx.fill();

        const { kind, ...params } = highlight;
        ctx.textAlign = 'left';
        ctx.fillStyle = palette.text;
        ctx.font = `bold 34px ${fonts.base}`;
        ctx.fillText(
          truncateToWidth(ctx, text(`matchShareCard.highlight.${kind}`, params), CONTENT_WIDTH - 64 - 24),
          textX,
          rowTop + (HIGHLIGHT_LINE - 34) / 2,
        );
      });
    },
  };
}

function drawFooter(
  ctx: ShareCardCanvas,
  model: ShareCardModel,
  palette: SharePalette,
  text: ShareCardText,
  fonts: ShareCardFonts,
): void {
  ctx.fillStyle = palette.divider;
  ctx.fillRect(SHARE_CARD_PADDING, FOOTER_TOP - 32, CONTENT_WIDTH, 2);

  ctx.textAlign = 'right';
  ctx.fillStyle = palette.text;
  ctx.font = `bold 32px ${fonts.base}`;
  const brand = text('matchShareCard.brand');
  ctx.fillText(brand, RIGHT_EDGE, FOOTER_TOP);
  const brandWidth = ctx.measureText(brand).width;

  const parts: string[] = [];
  if (model.durationSeconds !== null) {
    parts.push(durationText(model.durationSeconds, text));
  }
  if (model.averagePointSeconds !== null) {
    parts.push(
      text('matchShareCard.avgPerPoint', { seconds: Math.round(model.averagePointSeconds) }),
    );
  }
  if (parts.length > 0) {
    ctx.textAlign = 'left';
    ctx.fillStyle = palette.textMuted;
    ctx.font = `28px ${fonts.base}`;
    ctx.fillText(
      truncateToWidth(ctx, parts.join(' · '), CONTENT_WIDTH - brandWidth - 32),
      SHARE_CARD_PADDING,
      FOOTER_TOP + 2,
    );
  }
}

function durationText(seconds: number, text: ShareCardText): string {
  if (seconds >= 3600) {
    return text('matchShareCard.durationHours', {
      hours: Math.floor(seconds / 3600),
      minutes: Math.floor((seconds % 3600) / 60),
    });
  }
  return text('matchShareCard.duration', {
    minutes: Math.floor(seconds / 60),
    seconds: seconds % 60,
  });
}

function panel(
  ctx: ShareCardCanvas,
  x: number,
  y: number,
  width: number,
  height: number,
  color: string,
): void {
  roundedFill(ctx, x, y, width, height, 24, color);
}

function pill(
  ctx: ShareCardCanvas,
  x: number,
  y: number,
  width: number,
  height: number,
  color: string,
): void {
  roundedFill(ctx, x, y, width, height, height / 2, color);
}

function roundedFill(
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
