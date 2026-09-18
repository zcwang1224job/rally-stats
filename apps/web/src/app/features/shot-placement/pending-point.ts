import { Team } from '../../core/api/court-live-state.models';
import { ShotPlacementConfirmed } from './shot-placement-picker.component';

/** What the scorer did in the picker for this point. */
export type PendingPointAction =
  | { kind: 'confirm'; detail: ShotPlacementConfirmed }
  | { kind: 'cancel' };

/** One "+" press whose picker is open (or was) — the picker now opens the
 * instant "+" is tapped instead of after the score request returns, so the
 * scorer can finish in the picker before the point's score_event_id is
 * known. Whatever they do before then is held here and handed back once
 * the request resolves; after that it's acted on straight away. Shared by
 * every screen that scores. */
export class PendingPoint {
  scoreEventId: string | null = null;
  /** The point decided the match — cancelling it needs the undo-completion
   * endpoint, not a plain −1. Known only once the request resolves. */
  matchCompleted = false;
  private queued: PendingPointAction | null = null;

  constructor(
    readonly matchId: string,
    readonly side: Team,
  ) {}

  get resolved(): boolean {
    return this.scoreEventId !== null;
  }

  /** The score request came back applied. Returns the action taken while
   * it was in flight, if any, for the caller to run now. */
  resolve(scoreEventId: string, matchCompleted: boolean): PendingPointAction | null {
    this.scoreEventId = scoreEventId;
    this.matchCompleted = matchCompleted;
    const queued = this.queued;
    this.queued = null;
    return queued;
  }

  /** True if the caller should run `action` now; false if it was queued
   * until resolve(). */
  request(action: PendingPointAction): boolean {
    if (this.resolved) {
      return true;
    }
    this.queued = action;
    return false;
  }
}
