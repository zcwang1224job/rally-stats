import { SharePalette, ShareTheme } from './share-card-canvas';

/** 040-match-share-card research.md Decision 10: the card carries its own
 * colors (the app itself has no dark theme). Team colors match
 * `--color-team-a-bg` / `--color-team-b-bg` in styles/_tokens.scss. */
const LIGHT: SharePalette = {
  background: '#ffffff',
  text: '#15171c',
  textMuted: '#5b6170',
  divider: '#e3e6ec',
  teamA: '#b3335f',
  teamB: '#35519e',
  panel: '#f4f5f8',
  badgeBackground: '#15171c',
  badgeText: '#ffffff',
  badgeMutedBackground: '#e3e6ec',
  badgeMutedText: '#15171c',
  trendA: '#b3335f',
  trendB: '#35519e',
};

/** The team colors are lifted so they still stand out on a dark card. */
const DARK: SharePalette = {
  background: '#121418',
  text: '#f3f4f6',
  textMuted: '#a7adba',
  divider: '#2a2e37',
  teamA: '#f06f9a',
  teamB: '#8aa4f5',
  panel: '#1d2129',
  badgeBackground: '#f3f4f6',
  badgeText: '#121418',
  badgeMutedBackground: '#2e333d',
  badgeMutedText: '#f3f4f6',
  trendA: '#f06f9a',
  trendB: '#8aa4f5',
};

export const SHARE_PALETTES: Record<ShareTheme, SharePalette> = {
  light: LIGHT,
  dark: DARK,
};
