import type { WaitingReason } from './api/court-live-state.models';

/** 037-rest-ready-toggle: the one place a court's `waiting_reason` becomes
 * text, used by every screen that shows an idle court. `member` uses the
 * member page's own wording for the two original reasons.
 *
 * Exhaustive over `WaitingReason`, and any value it doesn't know (a newer
 * backend) falls back to "waiting for the next round" rather than showing
 * nothing. */
const KEYS: Record<WaitingReason, { court: string; member: string }> = {
  manual_assignment: {
    court: 'scheduleManagement.waitingManualAssignment',
    member: 'groupMemberView.schedule.waitingManualAssignment',
  },
  no_queued_match: {
    court: 'scheduleManagement.waitingNoQueuedMatch',
    member: 'groupMemberView.schedule.waitingNoQueuedMatch',
  },
  held_for_rest: {
    court: 'scheduleManagement.waitingHeldForRest',
    member: 'scheduleManagement.waitingHeldForRest',
  },
  not_enough_ready: {
    court: 'scheduleManagement.waitingNotEnoughReady',
    member: 'scheduleManagement.waitingNotEnoughReady',
  },
};

export function waitingReasonKey(
  reason: WaitingReason | string | null | undefined,
  scope: 'court' | 'member' = 'court',
): string {
  const known = reason && reason in KEYS ? KEYS[reason as WaitingReason] : KEYS.no_queued_match;
  return known[scope];
}
