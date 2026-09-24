/** How long a score button stays locked after its request comes back. It
 * outlasts the server's post-response Ably send (~65 ms), so two quick
 * taps can't also race each other's realtime events. */
export const SCORE_TAP_COOLDOWN_MS = 400;

/** Stops a quick double-tap on "+" / "−" from scoring twice: one score
 * request at a time per court, plus a short cooldown after each one returns.
 * A tap while locked is simply dropped — the scorer sees the first one land
 * and can tap again. Shared by every screen that scores (control panel,
 * all-courts block, scoreboard). */
export class ScoreTapGuard {
  private inFlight = false;
  private lockedUntil = 0;

  constructor(private readonly cooldownMs = SCORE_TAP_COOLDOWN_MS) {}

  /** True (and now locked) if a new score request may go out. */
  tryAcquire(): boolean {
    if (this.inFlight || Date.now() < this.lockedUntil) {
      return false;
    }
    this.inFlight = true;
    return true;
  }

  /** Locks without asking — for a follow-up that belongs to a point already
   * underway (the picker's "cancel score"), which must never be dropped. */
  hold(): void {
    this.inFlight = true;
  }

  /** The request came back (or failed): start the cooldown. */
  release(): void {
    this.inFlight = false;
    this.lockedUntil = Date.now() + this.cooldownMs;
  }
}
