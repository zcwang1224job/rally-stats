const KEY_PREFIX = 'rally-stats:score-swap:';

/** Per-viewer, per-court "which team is shown on which side" preference for
 * the scoring control panels — lets whoever's scoring flip the left/right
 * arrangement to match their own habit, remembered per court (not globally)
 * since different physical courts may warrant different arrangements. */
export function getScoreSwapPreference(courtKey: string): boolean {
  return localStorage.getItem(KEY_PREFIX + courtKey) === '1';
}

export function setScoreSwapPreference(courtKey: string, swapped: boolean): void {
  localStorage.setItem(KEY_PREFIX + courtKey, swapped ? '1' : '0');
}
