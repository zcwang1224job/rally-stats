// 034-clutch-points-player-dashboard: a member's cross-match technique
// dashboard (`GET /members/me/match-dashboard`, and the same shape for a
// friend's). Every number arrives computed — including whether a change is
// progress — so the frontend only formats and lays out. null / [] IS the
// "no data" signal, never an all-zero structure.

export const DASHBOARD_METRIC_KEYS = [
  'team_serve',
  'team_receive',
  'own_serve',
  'own_receive',
  'points_scored',
  'points_lost',
  'scored_lost_ratio',
  'endgame',
  'deuce',
  'match_point_conversion',
  'match_points_saved',
  'when_leading',
  'when_tied',
  'when_trailing',
  'avg_points_for',
  'avg_points_against',
  'avg_win_margin',
  'avg_loss_margin',
  // 035-point-ending-type: appended, never reordered (mirrors _METRICS).
  'winner_share',
  'winners_per_match',
  'errors_per_match',
  'error_share_of_lost',
  'winner_error_ratio',
] as const;

export type DashboardMetricKey = (typeof DASHBOARD_METRIC_KEYS)[number];

// rate: won / played, shown as a percentage. average: a count per match.
// ratio: one count over another.
export type DashboardMetricKind = 'rate' | 'average' | 'ratio';

export type DashboardVerdict = 'improved' | 'declined' | 'unchanged' | 'insufficient';

export interface DashboardMetricValue {
  // null with matches_used > 0: the metric applies but its denominator is 0
  // (e.g. never trailed) — shown as "0/0 —", never as 0%.
  value: number | null;
  numerator: number;
  denominator: number;
  matches_used: number;
}

export interface DashboardMetric {
  key: DashboardMetricKey;
  kind: DashboardMetricKind;
  // null: no direction (saving many match points also means facing many).
  better_when: 'higher' | 'lower' | null;
  all: DashboardMetricValue | null; // null: no match has this metric's data
  recent: DashboardMetricValue | null; // null: no comparison is shown
  verdict: DashboardVerdict | null;
}

export interface DashboardTrendPoint {
  from_ended_at: string;
  to_ended_at: string;
  value: number | null;
  numerator: number;
  denominator: number;
}

export interface DashboardTrend {
  key: DashboardMetricKey;
  points: DashboardTrendPoint[]; // oldest first
}

export type DashboardLandingPoint = [x: number, y: number];

export interface DashboardLanding {
  // Newest match first, already turned so the member's own side is on the
  // left (x < 0.5): the recent range is `scored.slice(0, recent_scored_count)`.
  scored: DashboardLandingPoint[];
  lost: DashboardLandingPoint[];
  // Every point credited/charged to the member, plotted or not.
  scored_total: number;
  lost_total: number;
  matches_used: number;
  recent_scored_count: number;
  recent_lost_count: number;
  recent_scored_total: number;
  recent_lost_total: number;
  recent_matches_used: number;
}

// 035-point-ending-type: the member's own errors by kind.
export interface DashboardErrorsByType {
  out: number;
  net: number;
  serve_fault: number;
  other_error: number;
}

export interface DashboardErrorBreakdown {
  all: DashboardErrorsByType;
  // null whenever there is no comparison (total_matches <= recent_window).
  recent: DashboardErrorsByType | null;
}

export interface MemberMatchDashboardResponse {
  total_matches: number;
  recent_window: number;
  has_comparison: boolean;
  metrics: DashboardMetric[]; // [] iff total_matches === 0, otherwise all 23
  trends: DashboardTrend[]; // only metrics with enough matches for a trend
  landing: DashboardLanding | null;
  // 035: null when not one of the member's errors was ever recorded.
  error_breakdown: DashboardErrorBreakdown | null;
  // 036: follows the same filters as `metrics`.
  insights: DashboardInsights;
}

// 036-match-insights-benchmarks US1. The backend decides WHICH insights and
// in what order and sends a rule code plus the numbers behind it; the wording
// lives in the locale files (playerInsights.rule.<rule>.*). Same eight codes,
// same order, as specs/036-…/data-model.md 規則表 and the backend's
// `InsightRule` — each end has a test pinning it to that list.
export const INSIGHT_RULES = [
  'rate_vs_overall',
  'deuce_vs_even',
  'error_share_high',
  'winner_share_high',
  'recent_change',
  'partner_above_overall',
  'opponent_below_overall',
  'benchmark_quartile',
] as const;
export type InsightRule = (typeof INSIGHT_RULES)[number];
export type InsightList = 'strength' | 'weakness' | 'recent' | 'matchup';
export type InsightLevel = 'strong' | 'mild';
export type InsightSource = 'benchmark' | 'self' | 'trend' | 'matchup';
export type InsightStatus = 'ok' | 'insufficient_data' | 'balanced';

export interface DashboardInsightPlayer {
  key: string;
  nickname: string;
  member_id: string | null;
}

export interface DashboardInsight {
  list: InsightList;
  rule: InsightRule;
  level: InsightLevel;
  source: InsightSource;
  metric_key: DashboardMetricKey | null;
  player: DashboardInsightPlayer | null;
  // Every number here is one the dashboard (or the partner/opponent table)
  // also shows — quoted, never recomputed.
  params: Record<string, number | string | null>;
}

export interface DashboardInsights {
  // insufficient_data: no rule had enough to go on. balanced: some did, and
  // nothing stood out. Either way the four lists are empty.
  status: InsightStatus;
  // Only the group-benchmark response sets this (its insights merge in the
  // in-group source); always null on the dashboard responses.
  benchmark_group_name: string | null;
  strengths: DashboardInsight[];
  weaknesses: DashboardInsight[];
  recent: DashboardInsight[];
  matchups: DashboardInsight[];
}
