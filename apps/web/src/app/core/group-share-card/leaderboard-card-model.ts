import { formatDate } from '@angular/common';
import { MemberGroupHistoryResponse } from '../api/friend.models';
import { FinalStandingRow } from '../api/group-member-view.models';
import type { TranslatedText } from '../share-card/share-card-canvas';
import { GroupShareCardContext, LeaderboardCardModel, LeaderboardRow } from './group-share-card.models';

const TOP_ROWS = 6;
const PODIUM_ROWS = 3;
const FILE_NAME_GROUP_LENGTH = 40;

/** 041-group-share-cards contracts/group-share-card.md §1 (L1–L10). The
 * standings arrive ranked and ordered by the server; this only keeps the
 * players who played, takes the first six and picks out mine — it never
 * sorts, re-ranks or renumbers (FR-008, constitution X). Null when nobody
 * has played yet, so the card isn't offered (FR-005). */
export function buildLeaderboardCardModel(
  history: MemberGroupHistoryResponse,
  context: GroupShareCardContext,
): LeaderboardCardModel | null {
  const played = history.final_standings.filter(hasPlayed);
  if (played.length === 0) {
    return null;
  }
  const rows = played.slice(0, TOP_ROWS).map((row, index) => toRow(row, index < PODIUM_ROWS));
  const me = played.find((row) => row.is_self);
  const selfRow = me && !rows.some((row) => row.isSelf) ? toRow(me, false) : null;
  return {
    groupName: history.group_name,
    date: context.createdAt,
    playerCount: played.length,
    rows,
    selfRow,
    fileName: groupCardFileName('rank', history.group_name, context.createdAt),
    altText: altText(history.group_name, rows),
  };
}

/** Players with at least one completed match — the leaderboard's and the
 * "my stats" card's "of N players" (FR-006, FR-014). */
export function countPlayers(standings: readonly FinalStandingRow[]): number {
  return standings.filter(hasPlayed).length;
}

/** `rally-stats-<card>-<yyyyMMdd | nodate>-<group>.png`, with the group
 * name made safe for a file name and kept short (FR-032). The date is the
 * device's own calendar day, like everything else on the card. */
export function groupCardFileName(card: 'rank' | 'me', groupName: string, date: string | null): string {
  const day = date ? formatDate(date, 'yyyyMMdd', 'en-US') : 'nodate';
  const group =
    [...groupName.replace(/[/\\:*?"<>|\s]+/g, '-').replace(/^-+|-+$/g, '')]
      .slice(0, FILE_NAME_GROUP_LENGTH)
      .join('') || 'group';
  return `rally-stats-${card}-${day}-${group}.png`;
}

function hasPlayed(row: FinalStandingRow): boolean {
  return row.total_matches > 0;
}

/** Only what the card shows: no status, no ID (FR-011, FR-021). */
function toRow(row: FinalStandingRow, podium: boolean): LeaderboardRow {
  return {
    rank: row.rank,
    nickname: row.nickname,
    wins: row.total_wins,
    losses: row.total_losses,
    isSelf: row.is_self,
    podium,
  };
}

/** Names the top rows with the server's ranks, choosing the wording by
 * how many there are — never an empty name (FR-031). */
function altText(group: string, rows: LeaderboardRow[]): TranslatedText {
  const top = rows.slice(0, PODIUM_ROWS);
  const params: Record<string, string | number> = { group };
  top.forEach((row, index) => {
    params[`rank${index + 1}`] = row.rank;
    params[`name${index + 1}`] = row.nickname;
  });
  return { key: `groupShareCard.leaderboard.altText${top.length}`, params };
}
