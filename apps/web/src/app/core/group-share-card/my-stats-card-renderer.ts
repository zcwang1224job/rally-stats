import { formatDate } from '@angular/common';
import {
  SHARE_CARD_HEIGHT,
  SHARE_CARD_PADDING,
  SHARE_CARD_WIDTH,
  ShareCardCanvas,
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
import { MyStatsCardModel } from './group-share-card.models';

const CONTENT_WIDTH = SHARE_CARD_WIDTH - SHARE_CARD_PADDING * 2;
const RIGHT_EDGE = SHARE_CARD_WIDTH - SHARE_CARD_PADDING;

// contracts/group-share-card.md §2.
const NAME_LINE = 52;
const RATE_SIZE = 140;
const RATE_LINE = 150;
const RECORD_LINE = 30;
const STANDING_HEIGHT = 56;
const TREND_HEIGHT = 220;
const TREND_MIN_HEIGHT = 140;
const TREND_TITLE = 44;
const TREND_INSET = 24;
const OPPONENT_TITLE = 40;
const OPPONENT_ROW = 56;
const OPPONENT_RECORD_WIDTH = 200;

/** 041-group-share-cards US3: "my stats in this group" — the win rate big,
 * my record, my rank, a trend of each round and the players I met most.
 * A part with nothing to show is left out, never drawn empty (FR-017); the
 * trend is the one part that shrinks when the card is full. */
export function renderMyStatsCard(
  ctx: ShareCardCanvas,
  model: MyStatsCardModel,
  env: ShareCardRenderEnv,
): void {
  const { palette, text, fonts } = env;
  ctx.textBaseline = 'top';
  ctx.fillStyle = palette.background;
  ctx.fillRect(0, 0, SHARE_CARD_WIDTH, SHARE_CARD_HEIGHT);

  ctx.textAlign = 'left';
  ctx.fillStyle = palette.text;
  ctx.font = `bold 44px ${fonts.base}`;
  ctx.fillText(truncateToWidth(ctx, model.groupName, CONTENT_WIDTH), SHARE_CARD_PADDING, SHARE_CARD_PADDING);
  const subtitle = [
    text('groupShareCard.myStats.title'),
    model.date ? formatDate(model.date, text('shareCard.dateFormat'), 'en-US') : null,
  ]
    .filter((part): part is string => !!part)
    .join(' · ');
  ctx.fillStyle = palette.textMuted;
  ctx.font = `30px ${fonts.base}`;
  ctx.fillText(truncateToWidth(ctx, subtitle, CONTENT_WIDTH), SHARE_CARD_PADDING, SHARE_CARD_PADDING + 64);

  const blocks: Block[] = [heroBlock()];
  if (model.standing) {
    blocks.push(standingBlock(model.standing));
  }
  if (model.trend) {
    blocks.push(trendBlock(model.trend));
  }
  if (model.opponents.length > 0) {
    blocks.push(opponentsBlock());
  }
  stackBlocks(blocks, {
    top: SHARE_CARD_MIDDLE_TOP,
    bottom: SHARE_CARD_MIDDLE_BOTTOM,
    gap: SHARE_CARD_BLOCK_GAP,
    minGap: SHARE_CARD_BLOCK_MIN_GAP,
  });

  drawPromoFooter(ctx, env.footer, env);

  /** My name, the win rate as the card's biggest text, then W–L of N. */
  function heroBlock(): Block {
    const nameLine = model.nickname === null ? 0 : NAME_LINE;
    return {
      height: nameLine + RATE_LINE + RECORD_LINE,
      draw: (y) => {
        ctx.textAlign = 'left';
        if (model.nickname !== null) {
          ctx.fillStyle = palette.text;
          ctx.font = `bold 40px ${fonts.base}`;
          ctx.fillText(truncateToWidth(ctx, model.nickname, CONTENT_WIDTH), SHARE_CARD_PADDING, y);
        }
        ctx.fillStyle = palette.text;
        ctx.font = `bold ${RATE_SIZE}px ${fonts.score}`;
        ctx.fillText(model.winRate, SHARE_CARD_PADDING, y + nameLine + (RATE_LINE - RATE_SIZE) / 2);
        ctx.fillStyle = palette.textMuted;
        ctx.font = `30px ${fonts.base}`;
        ctx.fillText(
          truncateToWidth(
            ctx,
            text('groupShareCard.myStats.record', {
              wins: model.wins,
              losses: model.losses,
              matches: model.matches,
            }),
            CONTENT_WIDTH,
          ),
          SHARE_CARD_PADDING,
          y + nameLine + RATE_LINE,
        );
      },
    };
  }

  function standingBlock(standing: { rank: number; playerCount: number }): Block {
    return {
      height: STANDING_HEIGHT,
      draw: (y) => {
        ctx.font = `bold 28px ${fonts.base}`;
        const label = truncateToWidth(
          ctx,
          text('groupShareCard.myStats.standing', { rank: standing.rank, count: standing.playerCount }),
          CONTENT_WIDTH - 48,
        );
        const width = ctx.measureText(label).width + 48;
        pill(ctx, SHARE_CARD_PADDING, y, width, STANDING_HEIGHT, palette.panel);
        ctx.textAlign = 'left';
        ctx.fillStyle = palette.text;
        ctx.fillText(label, SHARE_CARD_PADDING + 24, y + (STANDING_HEIGHT - 28) / 2);
      },
    };
  }

  /** One line through each round's win rate, on a fixed 0–100% axis. */
  function trendBlock(points: { x: number; y: number }[]): Block {
    return {
      height: TREND_HEIGHT,
      minHeight: TREND_MIN_HEIGHT,
      draw: (y, height) => {
        ctx.textAlign = 'left';
        ctx.fillStyle = palette.textMuted;
        ctx.font = `30px ${fonts.base}`;
        ctx.fillText(text('groupShareCard.myStats.trendTitle'), SHARE_CARD_PADDING, y);
        const top = y + TREND_TITLE;
        panel(ctx, SHARE_CARD_PADDING, top, CONTENT_WIDTH, height - TREND_TITLE, palette.panel);
        const left = SHARE_CARD_PADDING + TREND_INSET;
        const plotTop = top + TREND_INSET;
        const width = CONTENT_WIDTH - TREND_INSET * 2;
        const plotHeight = height - TREND_TITLE - TREND_INSET * 2;
        const at = (point: { x: number; y: number }) => ({
          x: left + (point.x / 100) * width,
          y: plotTop + (point.y / 100) * plotHeight,
        });
        ctx.strokeStyle = palette.trendA;
        ctx.lineWidth = 6;
        ctx.lineJoin = 'round';
        ctx.beginPath();
        points.forEach((point, index) => {
          const { x, y: pointY } = at(point);
          if (index === 0) {
            ctx.moveTo(x, pointY);
          } else {
            ctx.lineTo(x, pointY);
          }
        });
        ctx.stroke();
        const end = at(points[points.length - 1]);
        ctx.fillStyle = palette.trendA;
        ctx.beginPath();
        ctx.arc(end.x, end.y, 9, 0, Math.PI * 2);
        ctx.fill();
      },
    };
  }

  /** The players I met most, with my record against each. */
  function opponentsBlock(): Block {
    return {
      height: OPPONENT_TITLE + model.opponents.length * OPPONENT_ROW,
      draw: (y) => {
        ctx.textAlign = 'left';
        ctx.fillStyle = palette.textMuted;
        ctx.font = `30px ${fonts.base}`;
        ctx.fillText(text('groupShareCard.myStats.opponentsTitle'), SHARE_CARD_PADDING, y);
        model.opponents.forEach((opponent, index) => {
          const rowTop = y + OPPONENT_TITLE + index * OPPONENT_ROW;
          ctx.textAlign = 'left';
          ctx.fillStyle = palette.text;
          ctx.font = `34px ${fonts.base}`;
          ctx.fillText(
            truncateToWidth(ctx, opponent.nickname, CONTENT_WIDTH - OPPONENT_RECORD_WIDTH - 24),
            SHARE_CARD_PADDING,
            rowTop + (OPPONENT_ROW - 34) / 2,
          );
          ctx.textAlign = 'right';
          ctx.fillStyle = palette.textMuted;
          ctx.font = `30px ${fonts.base}`;
          ctx.fillText(
            truncateToWidth(
              ctx,
              text('groupShareCard.myStats.opponentRecord', { wins: opponent.wins, losses: opponent.losses }),
              OPPONENT_RECORD_WIDTH,
            ),
            RIGHT_EDGE,
            rowTop + (OPPONENT_ROW - 30) / 2,
          );
        });
      },
    };
  }
}
