/** 039-match-point-confirm: would this side's NEXT point end the match?
 *
 * Mirrors the server's own win test — `match_wins()` in
 * apps/api/app/domains/schedule/service.py — applied to the score the side
 * would have after scoring:
 *
 *     score_x >= cap_score || (score_x >= target_score && score_x - score_y >= 2)
 *
 * **`deuce_threshold` takes no part in this.** It is not a parameter here
 * and the backend deliberately does not send it to the frontend: at 20-20
 * with a target of 21, the next point only makes it 21-20 — a one-point
 * lead, not a win — so no confirmation is due. Reaching the cap wins
 * outright regardless of margin. Using the deuce threshold here would make
 * the dialog fire at the wrong score.
 *
 * This is only ever used to decide whether to ASK first. The server remains
 * the sole authority on whether a match actually ends (constitution X), so
 * being wrong here costs at most one extra prompt or one missing prompt —
 * never an inconsistent score.
 */
export function isMatchPoint(
  scoringSideScore: number,
  opponentScore: number,
  targetScore: number | undefined,
  capScore: number | undefined,
): boolean {
  // An older backend doesn't send these; fall back to "never warn", which
  // is exactly how every screen behaved before this feature.
  if (targetScore === undefined || capScore === undefined) {
    return false;
  }
  const after = scoringSideScore + 1;
  return after >= capScore || (after >= targetScore && after - opponentScore >= 2);
}
