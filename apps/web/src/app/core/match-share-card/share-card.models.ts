import { Team } from '../../features/group-admin/schedule-management/schedule.models';
import type { ScoreTrendPoint } from '../match-record-detail/score-trend';

export type { ScoreTrendPoint };

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

export interface TranslatedText {
  key: string;
  params: Record<string, string | number>;
}

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

export type ShareTheme = 'light' | 'dark';

export interface SharePalette {
  background: string;
  text: string;
  textMuted: string;
  divider: string;
  teamA: string;
  teamB: string;
  /** Background of the highlight/trend panels. */
  panel: string;
  badgeBackground: string;
  badgeText: string;
  /** Muted badge for a defeat — still text, never color alone (FR-029). */
  badgeMutedBackground: string;
  badgeMutedText: string;
  trendA: string;
  trendB: string;
}

/** Looks up a language-file entry; wraps `TranslateService.instant` in the
 * app, a stub in tests. */
export type ShareCardText = (key: string, params?: Record<string, string | number>) => string;

export interface ShareCardFonts {
  base: string;
  score: string;
}

/** The part of `CanvasRenderingContext2D` the renderer uses — narrow enough
 * for a recording fake in tests (jsdom has no canvas, research.md
 * Decision 3). */
export interface ShareCardCanvas {
  fillStyle: string | CanvasGradient | CanvasPattern;
  strokeStyle: string | CanvasGradient | CanvasPattern;
  lineWidth: number;
  lineJoin: CanvasLineJoin;
  font: string;
  textAlign: CanvasTextAlign;
  textBaseline: CanvasTextBaseline;
  fillRect(x: number, y: number, w: number, h: number): void;
  fillText(text: string, x: number, y: number): void;
  measureText(text: string): { width: number };
  beginPath(): void;
  moveTo(x: number, y: number): void;
  lineTo(x: number, y: number): void;
  stroke(): void;
  arc(x: number, y: number, radius: number, startAngle: number, endAngle: number): void;
  fill(): void;
  /** Missing before iOS Safari 16 — the renderer falls back to a square
   * corner path. */
  roundRect?(x: number, y: number, w: number, h: number, radii: number): void;
  save(): void;
  restore(): void;
}
