import type { TranslatedText } from '../share-card/share-card-canvas';

/** 041-group-share-cards data-model.md §3: what the group history page knows
 * that its history response doesn't. */
export interface GroupShareCardContext {
  /** When the group was created (ISO) — the card's date; null when the
   * group list couldn't be read (research.md Decision 7). */
  createdAt: string | null;
}

/** One leaderboard row. Holds no status and no ID (FR-011, FR-021). */
export interface LeaderboardRow {
  /** The server's rank, as given — ties included (FR-008). */
  rank: number;
  nickname: string;
  wins: number;
  losses: number;
  isSelf: boolean;
  /** The first three rows, by position — not by rank (research.md
   * Decision 3). */
  podium: boolean;
}

export interface LeaderboardCardModel {
  groupName: string;
  date: string | null;
  /** Players with at least one completed match. */
  playerCount: number;
  /** The first six players who played, in the server's order. */
  rows: LeaderboardRow[];
  /** My own row when I played but am not in `rows`. */
  selfRow: LeaderboardRow | null;
  fileName: string;
  altText: TranslatedText;
}
