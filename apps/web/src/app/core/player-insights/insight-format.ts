import { formatPercent } from '../match-record-detail/ratio-format';
import { DashboardInsight, InsightRule } from '../api/player-dashboard.models';

/** 036 US1: which sentence a rule code maps to, and how its numbers are
 * written. Nothing here decides anything — which insights exist, their
 * order and their strength all arrive from the backend; this only picks the
 * wording for what it was given.
 *
 * `satisfies Record<InsightRule, …>`: a rule added to INSIGHT_RULES without
 * its sentences is a compile error, not a blank line on the page. */
export const INSIGHT_VARIANTS = {
  rate_vs_overall: ['strength', 'weakness'],
  deuce_vs_even: ['strength', 'weakness'],
  error_share_high: ['weakness', 'weaknessDominant'],
  winner_share_high: ['strength'],
  recent_change: ['improved', 'declined'],
  partner_above_overall: ['matchup'],
  opponent_below_overall: ['matchup'],
  benchmark_quartile: ['strength', 'weakness'],
} as const satisfies Record<InsightRule, readonly string[]>;

export type InsightEvidence = 'points' | 'recent' | 'matchup' | 'benchmark';

export function insightVariant(insight: DashboardInsight): string {
  switch (insight.rule) {
    case 'recent_change':
      return insight.params['direction'] === 'declined' ? 'declined' : 'improved';
    case 'error_share_high':
      return insight.params['dominant_error'] ? 'weaknessDominant' : 'weakness';
    case 'partner_above_overall':
    case 'opponent_below_overall':
      return 'matchup';
    default:
      return insight.list === 'weakness' ? 'weakness' : 'strength';
  }
}

export function insightSentenceKey(insight: DashboardInsight): string {
  return `playerInsights.rule.${insight.rule}.${insightVariant(insight)}`;
}

export function insightEvidence(insight: DashboardInsight): InsightEvidence {
  switch (insight.rule) {
    case 'recent_change':
      return 'recent';
    case 'partner_above_overall':
    case 'opponent_below_overall':
      return 'matchup';
    case 'benchmark_quartile':
      return 'benchmark';
    default:
      return 'points';
  }
}

/** A share of points or matches, as a whole percentage — the same rounding
 * the metric cards use, so a sentence never disagrees with its card. */
export function percent(value: number | string | null | undefined): string {
  return typeof value === 'number' ? formatPercent(value) : '—';
}

/** A per-match count or a ratio: one decimal, like the metric cards. */
export function plain(value: number | string | null | undefined): string {
  return typeof value === 'number' ? value.toFixed(1) : '—';
}

/** Percentage points between two shares, unsigned — the sentence itself says
 * "above" or "below". */
export function points(value: number | string | null | undefined): string {
  return typeof value === 'number' ? `${Math.round(Math.abs(value) * 100)}` : '—';
}

/** `kind` travels with the rules whose metric may be a rate or a count. */
export function byKind(insight: DashboardInsight, value: number | string | null | undefined): string {
  return insight.params['kind'] === 'rate' ? percent(value) : plain(value);
}
