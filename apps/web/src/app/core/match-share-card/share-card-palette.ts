import { SharePalette, ShareTheme } from './share-card.models';

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

export const SHARE_PALETTES: Record<ShareTheme, SharePalette> = {
  light: LIGHT,
  // US5 (T048) gives dark its own colors.
  dark: LIGHT,
};
