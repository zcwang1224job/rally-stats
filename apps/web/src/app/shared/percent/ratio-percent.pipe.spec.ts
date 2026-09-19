import { formatPercent, percentOrDash } from '../../core/match-record-detail/ratio-format';
import { RatioPercentPipe } from './ratio-percent.pipe';

describe('formatPercent / RatioPercentPipe', () => {
  it('writes a 0–1 ratio as a whole percentage', () => {
    expect(formatPercent(0)).toBe('0%');
    expect(formatPercent(1)).toBe('100%');
    expect(formatPercent(0.625)).toBe('63%');
    expect(formatPercent(0.284)).toBe('28%');
  });

  it('is what the pipe and percentOrDash use', () => {
    expect(new RatioPercentPipe().transform(0.625)).toBe('63%');
    expect(percentOrDash(5, 8)).toBe('63%');
    expect(percentOrDash(0, 0)).toBe('—');
  });
});
