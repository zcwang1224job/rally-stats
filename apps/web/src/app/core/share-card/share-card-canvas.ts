/** 041-group-share-cards: the canvas-level vocabulary every card shares —
 * moved here from 040's `match-share-card/share-card.models.ts`, which
 * re-exports it so its own imports keep working. */

export const SHARE_CARD_WIDTH = 1080;
export const SHARE_CARD_HEIGHT = 1350;
export const SHARE_CARD_PADDING = 72;

export interface TranslatedText {
  key: string;
  params: Record<string, string | number>;
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
  /** The QR code's plate and modules: white and near-black in both themes
   * — an inverted code doesn't scan everywhere (041 research.md Decision 5). */
  qrPlate: string;
  qrModule: string;
}

/** Looks up a language-file entry; wraps `TranslateService.instant` in the
 * app, a stub in tests. */
export type ShareCardText = (key: string, params?: Record<string, string | number>) => string;

export interface ShareCardFonts {
  base: string;
  score: string;
}

/** The part of `CanvasRenderingContext2D` the renderers use — narrow enough
 * for a recording fake in tests (jsdom has no canvas, 040 research.md
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
