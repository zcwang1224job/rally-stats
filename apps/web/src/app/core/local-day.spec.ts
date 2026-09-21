import { localDayStart } from './local-day';

// Written to hold in whatever zone the tests run in: they read the result
// back through the LOCAL getters rather than comparing ISO strings.
describe('localDayStart', () => {
  it('is LOCAL midnight of that day — not UTC midnight', () => {
    const start = new Date(localDayStart('2026-09-21')!);

    expect([start.getFullYear(), start.getMonth(), start.getDate()]).toEqual([2026, 8, 21]);
    expect([start.getHours(), start.getMinutes(), start.getSeconds()]).toEqual([0, 0, 0]);
  });

  it('rolls over month and year ends when offset by a day', () => {
    const afterSeptember = new Date(localDayStart('2026-09-30', 1)!);
    const afterDecember = new Date(localDayStart('2026-12-31', 1)!);

    expect([afterSeptember.getMonth(), afterSeptember.getDate()]).toEqual([9, 1]);
    expect([afterDecember.getFullYear(), afterDecember.getMonth(), afterDecember.getDate()]).toEqual(
      [2027, 0, 1],
    );
  });

  it('carries a UTC offset, which the API requires', () => {
    expect(localDayStart('2026-09-21')).toMatch(/Z$/);
  });

  it('is undefined for an empty or malformed value', () => {
    expect(localDayStart('')).toBeUndefined();
    expect(localDayStart('2026/09/21')).toBeUndefined();
  });
});
