/** The instant a LOCAL calendar day (`<input type="date">`'s `YYYY-MM-DD`)
 * begins, `offsetDays` days later, as an ISO string — or undefined for an
 * empty/unparseable value.
 *
 * Every date-range filter sends its days through this, because the API
 * takes half-open ranges of INSTANTS (`*_from` <= t < `*_before`), not
 * calendar dates: an inclusive "to" day is `localDayStart(to, 1)`. The
 * times a list shows are the viewer's local times, so the filter has to
 * mean the viewer's local day too — a match finished (or a group opened)
 * at 07:30 Taipei time belongs to that day, not to the previous day's UTC
 * date, which is what comparing a bare date on the server would give.
 *
 * Built from the date's parts so it is LOCAL midnight — `new
 * Date('YYYY-MM-DD')` would be UTC midnight — and DST-safe, since the day
 * after is asked for as a calendar day rather than as "+24 hours". */
export function localDayStart(date: string, offsetDays = 0): string | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) {
    return undefined;
  }
  const [year, month, day] = match.slice(1).map(Number);
  return new Date(year, month - 1, day + offsetDays).toISOString();
}
