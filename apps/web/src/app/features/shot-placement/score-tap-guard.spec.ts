import { SCORE_TAP_COOLDOWN_MS, ScoreTapGuard } from './score-tap-guard';

describe('ScoreTapGuard', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('lets one request out, then refuses until it is released', () => {
    const guard = new ScoreTapGuard();

    expect(guard.tryAcquire()).toBe(true);
    expect(guard.tryAcquire()).toBe(false);
  });

  it('keeps refusing for the cooldown after a release, then opens again', () => {
    const guard = new ScoreTapGuard();
    guard.tryAcquire();
    guard.release();

    vi.advanceTimersByTime(SCORE_TAP_COOLDOWN_MS - 1);
    expect(guard.tryAcquire()).toBe(false);

    vi.advanceTimersByTime(1);
    expect(guard.tryAcquire()).toBe(true);
  });

  it('hold() locks even during the cooldown — a follow-up is never dropped', () => {
    const guard = new ScoreTapGuard();
    guard.tryAcquire();
    guard.release();

    guard.hold();
    vi.advanceTimersByTime(SCORE_TAP_COOLDOWN_MS);

    expect(guard.tryAcquire()).toBe(false);
  });
});
