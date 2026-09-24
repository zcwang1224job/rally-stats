import type { TranslatedText } from '../share-card/share-card-canvas';

/** 041-group-share-cards data-model.md §3: what the group history page knows
 * that its history response doesn't. */
export interface GroupShareCardContext {
  /** When the group was created (ISO) — the card's date; null when the
   * group list couldn't be read (research.md Decision 7). */
  createdAt: string | null;
  /** 043 US6: the activity's name (translation key or typed name); null
   * for badminton, whose cards stay as they were. */
  activity?: { key: string | null; name: string | null } | null;
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

/** 041 US3: "my stats in this group" — every number as the page shows it. */
export interface MyStatsCardModel {
  groupName: string;
  date: string | null;
  /** 043 US6: the activity's name (translation key or typed name); null
   * for badminton, whose cards stay as they were. */
  activity?: { key: string | null; name: string | null } | null;
  /** My name from my standings row; null (left out) when I'm not in it. */
  nickname: string | null;
  /** Exactly the page's wording, e.g. "60%" (FR-017). */
  winRate: string;
  wins: number;
  losses: number;
  matches: number;
  /** "#rank of N" — null when I'm not in the standings. */
  standing: { rank: number; playerCount: number } | null;
  /** One point per round on the page's fixed 0–100% axis: x and y are
   * 0–100, y = 0 at the top (FR-015). Null with fewer than two rounds. */
  trend: { x: number; y: number }[] | null;
  /** The first three of the page's opponent list, in its order (FR-016). */
  opponents: { nickname: string; wins: number; losses: number }[];
  fileName: string;
  altText: TranslatedText;
}

export interface LeaderboardCardModel {
  groupName: string;
  date: string | null;
  /** 043 US6: the activity's name (translation key or typed name); null
   * for badminton, whose cards stay as they were. */
  activity?: { key: string | null; name: string | null } | null;
  /** Players with at least one completed match. */
  playerCount: number;
  /** The first six players who played, in the server's order. */
  rows: LeaderboardRow[];
  /** My own row when I played but am not in `rows`. */
  selfRow: LeaderboardRow | null;
  fileName: string;
  altText: TranslatedText;
}
