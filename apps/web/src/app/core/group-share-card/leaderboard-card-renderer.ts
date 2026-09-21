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
import { LeaderboardCardModel, LeaderboardRow } from './group-share-card.models';
import { MEDAL_COLORS, MEDAL_TEXT } from './group-share-card-palette';

const CONTENT_WIDTH = SHARE_CARD_WIDTH - SHARE_CARD_PADDING * 2;

// Columns: rank (medal) · name · record, right-aligned in a fixed column so
// it never moves with the name's length (SC-005).
const RANK_CENTER_X = SHARE_CARD_PADDING + 48;
const NAME_X = SHARE_CARD_PADDING + 112;
const RECORD_RIGHT = SHARE_CARD_WIDTH - SHARE_CARD_PADDING - 24;
const RECORD_WIDTH = 200;
const NAME_MAX_WIDTH = RECORD_RIGHT - RECORD_WIDTH - 24 - NAME_X;

// contracts/group-share-card.md §2: row heights include their own spacing.
const PODIUM_ROW = 120;
const ROW = 76;
const SELF_DIVIDER = 40;

const TAG_HEIGHT = 40;
const TAG_FONT = 24;
const TAG_PAD = 16;

interface RowStyle {
  height: number;
  nameSize: number;
  nameBold: boolean;
  medalRadius: number;
  numberSize: number;
}

/** 041-group-share-cards US1: the group leaderboard — the first three rows
 * on a podium, rows four to six below, and my own row after a divider when
 * I'm further down. Ranks are drawn as numbers; a medal only decorates
 * ranks 1–3 (FR-009). */
export function renderLeaderboardCard(
  ctx: ShareCardCanvas,
  model: LeaderboardCardModel,
  env: ShareCardRenderEnv,
): void {
  const { palette, text, fonts } = env;
  ctx.textBaseline = 'top';
  ctx.fillStyle = palette.background;
  ctx.fillRect(0, 0, SHARE_CARD_WIDTH, SHARE_CARD_HEIGHT);

  // Header: group name, then "Leaderboard · date · N players". Never
  // "final": the group may still be playing (FR-012).
  ctx.textAlign = 'left';
  ctx.fillStyle = palette.text;
  ctx.font = `bold 44px ${fonts.base}`;
  ctx.fillText(truncateToWidth(ctx, model.groupName, CONTENT_WIDTH), SHARE_CARD_PADDING, SHARE_CARD_PADDING);
  const subtitle = [
    text('groupShareCard.leaderboard.title'),
    model.date ? formatDate(model.date, text('shareCard.dateFormat'), 'en-US') : null,
    text('groupShareCard.leaderboard.playerCount', { count: model.playerCount }),
  ]
    .filter((part): part is string => !!part)
    .join(' · ');
  ctx.fillStyle = palette.textMuted;
  ctx.font = `30px ${fonts.base}`;
  ctx.fillText(truncateToWidth(ctx, subtitle, CONTENT_WIDTH), SHARE_CARD_PADDING, SHARE_CARD_PADDING + 64);

  const podium: RowStyle = {
    height: PODIUM_ROW,
    nameSize: 44,
    nameBold: true,
    medalRadius: 36,
    numberSize: 36,
  };
  const regular: RowStyle = {
    height: ROW,
    nameSize: 36,
    nameBold: false,
    medalRadius: 28,
    numberSize: 28,
  };

  const blocks: Block[] = [];
  const onPodium = model.rows.filter((row) => row.podium);
  const below = model.rows.filter((row) => !row.podium);
  blocks.push(rowsBlock(onPodium, podium));
  if (below.length > 0) {
    blocks.push(rowsBlock(below, regular));
  }
  const self = model.selfRow;
  if (self) {
    blocks.push({
      height: SELF_DIVIDER + ROW,
      draw: (y) => {
        ctx.textAlign = 'center';
        ctx.fillStyle = palette.textMuted;
        ctx.font = `30px ${fonts.base}`;
        ctx.fillText('⋯', SHARE_CARD_WIDTH / 2, y + 4);
        drawRow(self, y + SELF_DIVIDER, regular);
      },
    });
  }
  stackBlocks(blocks, {
    top: SHARE_CARD_MIDDLE_TOP,
    bottom: SHARE_CARD_MIDDLE_BOTTOM,
    gap: SHARE_CARD_BLOCK_GAP,
    minGap: SHARE_CARD_BLOCK_MIN_GAP,
  });

  drawPromoFooter(ctx, env.footer, env);

  function rowsBlock(rows: LeaderboardRow[], style: RowStyle): Block {
    return {
      height: rows.length * style.height,
      draw: (y) => rows.forEach((row, index) => drawRow(row, y + index * style.height, style)),
    };
  }

  function drawRow(row: LeaderboardRow, top: number, style: RowStyle): void {
    const middle = top + style.height / 2;
    if (row.isSelf) {
      panel(ctx, SHARE_CARD_PADDING, top + 6, CONTENT_WIDTH, style.height - 12, palette.panel);
    }

    // Rank: a number, on a medal for 1–3.
    ctx.textAlign = 'center';
    const medal = row.rank <= 3 ? MEDAL_COLORS[row.rank as 1 | 2 | 3] : null;
    if (medal) {
      ctx.fillStyle = medal;
      ctx.beginPath();
      ctx.arc(RANK_CENTER_X, middle, style.medalRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = MEDAL_TEXT;
      ctx.font = `bold ${style.numberSize}px ${fonts.base}`;
      ctx.fillText(String(row.rank), RANK_CENTER_X, middle - style.numberSize / 2);
    } else {
      ctx.fillStyle = palette.textMuted;
      ctx.font = `bold 32px ${fonts.base}`;
      ctx.fillText(String(row.rank), RANK_CENTER_X, middle - 16);
    }

    // "Me" is a word on a pill, not just a color (FR-010).
    let tagWidth = 0;
    let tagLabel = '';
    if (row.isSelf) {
      ctx.font = `bold ${TAG_FONT}px ${fonts.base}`;
      tagLabel = text('groupShareCard.selfTag');
      tagWidth = ctx.measureText(tagLabel).width + TAG_PAD * 2;
    }

    ctx.textAlign = 'left';
    ctx.fillStyle = palette.text;
    ctx.font = `${style.nameBold ? 'bold ' : ''}${style.nameSize}px ${fonts.base}`;
    const name = truncateToWidth(
      ctx,
      row.nickname,
      NAME_MAX_WIDTH - (row.isSelf ? tagWidth + TAG_PAD : 0),
    );
    ctx.fillText(name, NAME_X, middle - style.nameSize / 2);

    if (row.isSelf) {
      const tagX = NAME_X + ctx.measureText(name).width + TAG_PAD;
      pill(ctx, tagX, middle - TAG_HEIGHT / 2, tagWidth, TAG_HEIGHT, palette.badgeBackground);
      ctx.fillStyle = palette.badgeText;
      ctx.font = `bold ${TAG_FONT}px ${fonts.base}`;
      ctx.fillText(tagLabel, tagX + TAG_PAD, middle - TAG_FONT / 2);
    }

    ctx.textAlign = 'right';
    ctx.fillStyle = palette.textMuted;
    ctx.font = `30px ${fonts.base}`;
    ctx.fillText(
      truncateToWidth(
        ctx,
        text('groupShareCard.leaderboard.record', { wins: row.wins, losses: row.losses }),
        RECORD_WIDTH,
      ),
      RECORD_RIGHT,
      middle - 15,
    );
  }
}
