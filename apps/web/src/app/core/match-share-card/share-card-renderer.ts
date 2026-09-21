import { formatDate } from '@angular/common';
import {
  SHARE_CARD_HEIGHT,
  SHARE_CARD_PADDING,
  SHARE_CARD_WIDTH,
} from '../share-card/share-card-canvas';
import { panel, pill, truncateToWidth } from '../share-card/share-card-drawing';
import { drawPromoFooter } from '../share-card/share-card-footer';
import {
  Block,
  SHARE_CARD_BLOCK_GAP,
  SHARE_CARD_BLOCK_MIN_GAP,
  SHARE_CARD_MIDDLE_BOTTOM,
  SHARE_CARD_MIDDLE_TOP,
  stackBlocks,
} from '../share-card/share-card-layout';
import { ShareCardRenderEnv } from '../share-card/share-card-option';
import {
  CardTeam,
  ScoreTrendPoint,
  ShareCardCanvas,
  ShareCardFonts,
  ShareCardModel,
  ShareCardText,
  SharePalette,
} from './share-card.models';

// 041-group-share-cards: these now live in the shared layer.
export { SHARE_CARD_HEIGHT, SHARE_CARD_PADDING, SHARE_CARD_WIDTH };

const CONTENT_WIDTH = SHARE_CARD_WIDTH - SHARE_CARD_PADDING * 2;
const RIGHT_EDGE = SHARE_CARD_WIDTH - SHARE_CARD_PADDING;
// The gap between the two teams inside the teams block (not between blocks).
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

/** 040-match-share-card: draws the 1080×1350 card (FR-004). The header is
 * pinned to the top and the footer to the bottom; the middle blocks are
 * stacked between them by the shared `stackBlocks()` (041), and a block
 * with nothing to show is simply not in the stack — no empty frame, no
 * placeholder (FR-009). The footer is the shared one, with this card's
 * duration and pace as its meta line. */
export function renderShareCard(
  ctx: ShareCardCanvas,
  model: ShareCardModel,
  env: ShareCardRenderEnv,
): void {
  const { palette, text, fonts } = env;
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
  stackBlocks(blocks, {
    top: SHARE_CARD_MIDDLE_TOP,
    bottom: SHARE_CARD_MIDDLE_BOTTOM,
    gap: SHARE_CARD_BLOCK_GAP,
    minGap: SHARE_CARD_BLOCK_MIN_GAP,
  });

  drawPromoFooter(ctx, { ...env.footer, meta: footerMeta(model, text) }, env);
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
    ? formatDate(model.startedAt, text('shareCard.dateFormat'), 'en-US')
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
      // FR-016: on "my" card, my team sits on its own panel — the badge
      // already says Victory/Defeat, this makes the whole row mine.
      if (model.perspective === 'mine') {
        panel(ctx, SHARE_CARD_PADDING, y - 20, CONTENT_WIDTH, heights[0] + 40, palette.panel);
      }
      drawTeam(ctx, model.teams[0], y, heights[0], palette, text, fonts);
      // The panel already separates the two teams on "my" card; a divider
      // right under it would only crowd it.
      if (model.perspective !== 'mine') {
        const dividerY = y + heights[0] + BLOCK_GAP / 2;
        ctx.fillStyle = palette.divider;
        ctx.fillRect(SHARE_CARD_PADDING, dividerY - 1, CONTENT_WIDTH, 2);
      }
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

/** The footer's meta line: the match's duration and pace, or null when
 * neither is known (041 contracts/share-card-core.md §7 — composed here,
 * drawn by the shared footer). */
function footerMeta(model: ShareCardModel, text: ShareCardText): string | null {
  const parts: string[] = [];
  if (model.durationSeconds !== null) {
    parts.push(durationText(model.durationSeconds, text));
  }
  if (model.averagePointSeconds !== null) {
    parts.push(
      text('matchShareCard.avgPerPoint', { seconds: Math.round(model.averagePointSeconds) }),
    );
  }
  return parts.length > 0 ? parts.join(' · ') : null;
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
