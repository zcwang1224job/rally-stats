/** A 0–1 ratio as a whole percentage ("62%") — the one rounding every
 * rate in the app uses, so a card, a table row and a sentence about the
 * same number never disagree by a point. */
export function formatPercent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}

/** "—" for a zero total: 0% would claim a rate that was never measured
 * (033 FR-014, 034 FR-015). Shared by every block that shows won/total. */
export function percentOrDash(won: number, total: number): string {
  return total === 0 ? '—' : formatPercent(won / total);
}
