import type {
  ShareCardCanvas,
  ShareCardFonts,
  ShareCardText,
  SharePalette,
  TranslatedText,
} from './share-card-canvas';

/** 041-group-share-cards contracts/share-card-core.md §1: types only — no
 * implementation file is imported here, so the footer, link, QR, actions
 * and preview can all depend on this file without depending on each other.
 * These shapes are final from Phase 2 on. */

/** The `ref` value on the card's QR link, and the card kind (FR-019). */
export type ShareCardSource = 'card-rank' | 'card-me' | 'card-match';

export interface ShareCardLink {
  /** `${origin}/?ref=${source}` — carries no ID of any kind (FR-021). */
  qrUrl: string;
  /** The host alone, short enough to type in by hand. */
  displayUrl: string;
}

export interface QrMatrix {
  size: number;
  isDark(row: number, col: number): boolean;
}

export interface PromoFooter {
  link: ShareCardLink;
  /** Null when the code couldn't be made, or the URL is too long to draw
   * reliably (FR-020). */
  qr: QrMatrix | null;
  /** One extra line above the brand. `rasterize()` always leaves it null;
   * the match card fills in its duration and pace. */
  meta: string | null;
}

export interface ShareCardRenderEnv {
  palette: SharePalette;
  text: ShareCardText;
  fonts: ShareCardFonts;
  footer: PromoFooter;
}

export interface ShareCardOption {
  source: ShareCardSource;
  /** Language key of this card's button in the kind switch. */
  labelKey: string;
  fileName: string;
  altText: TranslatedText;
  /** Pure and synchronous: the same input always draws the same card. */
  draw(ctx: ShareCardCanvas, env: ShareCardRenderEnv): void;
}
