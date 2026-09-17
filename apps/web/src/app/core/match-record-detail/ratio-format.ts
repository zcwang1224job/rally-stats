/** "—" for a zero total: 0% would claim a rate that was never measured
 * (033 FR-014, 034 FR-015). Shared by every block that shows won/total. */
export function percentOrDash(won: number, total: number): string {
  return total === 0 ? '—' : `${Math.round((won / total) * 100)}%`;
}
