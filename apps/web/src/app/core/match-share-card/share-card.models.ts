import { Team } from '../../features/group-admin/schedule-management/schedule.models';
import type { ScoreTrendPoint } from '../match-record-detail/score-trend';
import type { TranslatedText } from '../share-card/share-card-canvas';

export type { ScoreTrendPoint };
// 041-group-share-cards: the canvas-level types now live in the shared
// share-card layer; re-exported so every existing import keeps working.
export type {
  ShareCardCanvas,
  ShareCardFonts,
  ShareCardText,
  SharePalette,
  ShareTheme,
  TranslatedText,
} from '../share-card/share-card-canvas';

/** 040-match-share-card: what the caller of the match detail dialog knows
 * that the detail response doesn't — the group's name and which entry point
 * the dialog was opened from (clarify Q2: the perspective is decided by the
 * entry point alone, never by who is logged in). */
export interface ShareCardContext {
  groupName: string;
  perspective: { kind: 'neutral' } | { kind: 'mine'; myTeam: Team };
}

export type CardBadge = 'win' | 'victory' | 'defeat';

export interface CardTeam {
  /** The original side — keeps score, names and team color together after
   * the two teams are reordered for the card (FR-019). */
  team: Team;
  nicknames: string[];
  score: number;
  isWinner: boolean;
  badge: CardBadge | null;
}

/** research.md Decision 7: one entry per highlight candidate, in priority
 * order. The numbers are carried as-is; wording lives in the language files
 * under `matchShareCard.highlight.<kind>`. */
export type Highlight =
  | { kind: 'comeback'; deficit: number }
  | { kind: 'matchPointsSaved'; count: number }
  | { kind: 'deuceWin'; scoreFor: number; scoreAgainst: number }
  | { kind: 'run'; length: number }
  | { kind: 'winnerRate'; percent: string }
  | { kind: 'leadChanges'; count: number }
  | { kind: 'bigMargin'; margin: number };

export interface ShareCardModel {
  groupName: string;
  /** ISO timestamp; formatted into a date by the renderer. */
  startedAt: string | null;
  roundNumber: number;
  perspective: 'neutral' | 'mine';
  /** The first team is the card's protagonist: the winner (neutral) or the
   * viewer's own team (mine). */
  teams: [CardTeam, CardTeam];
  trend: ScoreTrendPoint[] | null;
  highlights: Highlight[];
  durationSeconds: number | null;
  averagePointSeconds: number | null;
  fileName: string;
  altText: TranslatedText;
}
