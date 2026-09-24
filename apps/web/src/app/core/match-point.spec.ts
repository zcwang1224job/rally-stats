import { isMatchPoint } from './match-point';

/** The boundary table from specs/039-match-point-confirm/data-model.md,
 * row for row. Target 21 / cap 30 throughout (the group defaults).
 *
 * The row that matters most is deuce: the backend's match_wins() does NOT
 * consult deuce_threshold, so 20-20 + 1 = 21-20 is a one-point lead and not
 * a win. Getting this wrong makes the confirm dialog fire a point early,
 * every single deuce. */
describe('isMatchPoint', () => {
  const TARGET = 21;
  const CAP = 30;

  it('a normal match point: 20-15, one more wins it', () => {
    expect(isMatchPoint(20, 15, TARGET, CAP)).toBe(true);
  });

  it('two points away: 19-15 would only reach 20', () => {
    expect(isMatchPoint(19, 15, TARGET, CAP)).toBe(false);
  });

  it('DEUCE: 20-20 is NOT match point — 21-20 leads by one, not two', () => {
    expect(isMatchPoint(20, 20, TARGET, CAP)).toBe(false);
  });

  it('past deuce: 21-20 IS match point — 22-20 clears the two-point margin', () => {
    expect(isMatchPoint(21, 20, TARGET, CAP)).toBe(true);
  });

  it('CAP: 29-29 IS match point — reaching 30 wins regardless of margin', () => {
    expect(isMatchPoint(29, 29, TARGET, CAP)).toBe(true);
  });

  it('one short of the cap: 28-29 reaches only 29, with no two-point lead', () => {
    expect(isMatchPoint(28, 29, TARGET, CAP)).toBe(false);
  });

  it('both sides at deuce: neither is at match point', () => {
    expect(isMatchPoint(20, 20, TARGET, CAP)).toBe(false);
    expect(isMatchPoint(20, 20, TARGET, CAP)).toBe(false); // symmetric
  });

  it('both sides one off the cap: BOTH are at match point', () => {
    expect(isMatchPoint(29, 29, TARGET, CAP)).toBe(true);
    expect(isMatchPoint(29, 29, TARGET, CAP)).toBe(true); // symmetric
  });

  it('a short game (target 15 / cap 21) shifts the boundaries with it', () => {
    expect(isMatchPoint(14, 9, 15, 21)).toBe(true);
    expect(isMatchPoint(13, 9, 15, 21)).toBe(false);
    expect(isMatchPoint(14, 14, 15, 21)).toBe(false); // deuce again
    expect(isMatchPoint(20, 20, 15, 21)).toBe(true); // cap again
  });

  it('an older backend sends neither rule: never warn, exactly as before', () => {
    expect(isMatchPoint(20, 15, undefined, CAP)).toBe(false);
    expect(isMatchPoint(20, 15, TARGET, undefined)).toBe(false);
    expect(isMatchPoint(20, 15, undefined, undefined)).toBe(false);
  });

  // 043: `null` cap means there is none — table tennis 11 points, lead by 2.
  it('no cap: only the win_by lead makes a match point, however long it runs', () => {
    expect(isMatchPoint(10, 8, 11, null)).toBe(true);
    expect(isMatchPoint(10, 10, 11, null)).toBe(false);
    expect(isMatchPoint(14, 13, 11, null)).toBe(true);
    expect(isMatchPoint(39, 39, 11, null)).toBe(false);
  });

  it('a one-point win_by (first to N frames) warns one frame out', () => {
    expect(isMatchPoint(4, 4, 5, null, 1)).toBe(true);
    expect(isMatchPoint(3, 4, 5, null, 1)).toBe(false);
  });
});
