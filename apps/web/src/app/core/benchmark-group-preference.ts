const KEY_PREFIX = 'rally-stats:benchmark-group:';

/** 036 FR-027: the group a member last chose to compare within — per member,
 * on this device. A UI preference, not match data, so it is not stored on the
 * server (research.md Decision 8); on another device the page simply falls
 * back to the default, the group with the most of their matches.
 *
 * Storage can be unavailable (private mode, blocked site data): a preference
 * that cannot be read or written must never break the page. */
export function getBenchmarkGroup(memberId: string | null): string | null {
  if (!memberId) {
    return null;
  }
  try {
    return localStorage.getItem(KEY_PREFIX + memberId);
  } catch {
    return null;
  }
}

export function setBenchmarkGroup(memberId: string | null, groupId: string): void {
  if (!memberId) {
    return;
  }
  try {
    localStorage.setItem(KEY_PREFIX + memberId, groupId);
  } catch {
    // Not remembered this time; nothing else depends on it.
  }
}
