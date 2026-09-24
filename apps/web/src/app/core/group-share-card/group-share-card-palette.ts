/** 041-group-share-cards contracts/group-share-card.md §2: medal colors are
 * the leaderboard's own, so they stay out of the shared palette. The same in
 * both themes — a medal reads as a medal on light and dark alike. The rank
 * number is written on the medal, so it never relies on color (FR-009). */
export const MEDAL_COLORS: Readonly<Record<1 | 2 | 3, string>> = {
  1: '#fcd34d',
  2: '#d1d5db',
  3: '#f4b183',
};

export const MEDAL_TEXT = '#111827';
