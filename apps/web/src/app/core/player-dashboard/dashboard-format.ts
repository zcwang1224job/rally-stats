import { DashboardMetricKind, DashboardMetricValue } from '../api/player-dashboard.models';
import { percentOrDash } from '../match-record-detail/ratio-format';

/** 034: how a dashboard number is written, in one place — the metric card,
 * the trend chart's readout and its table all go through this. A rate is a
 * whole percentage (same as the match detail's won/total cells); averages
 * and ratios keep one decimal. "—" for a missing value: 0 would claim
 * something that was never measured (FR-015). */
export function formatMetric(
  kind: DashboardMetricKind,
  value: Pick<DashboardMetricValue, 'value' | 'numerator' | 'denominator'>,
): string {
  if (value.value === null) {
    return '—';
  }
  return kind === 'rate'
    ? percentOrDash(value.numerator, value.denominator)
    : value.value.toFixed(1);
}

/** Signed difference between two values of the same metric, or null when
 * either side has no value. Rates differ in percentage points. "−" is the
 * real minus sign, so the number lines up with "+" in a column. */
export function formatDelta(
  kind: DashboardMetricKind,
  recent: number | null,
  overall: number | null,
): string | null {
  if (recent === null || overall === null) {
    return null;
  }
  const difference = kind === 'rate' ? (recent - overall) * 100 : recent - overall;
  const rounded = Math.abs(difference).toFixed(1);
  if (Number(rounded) === 0) {
    return '±0.0';
  }
  return `${difference > 0 ? '+' : '−'}${rounded}`;
}
