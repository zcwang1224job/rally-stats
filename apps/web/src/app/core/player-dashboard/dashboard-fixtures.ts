import {
  DASHBOARD_METRIC_KEYS,
  DashboardMetric,
  DashboardMetricKey,
  DashboardMetricKind,
  MemberMatchDashboardResponse,
} from '../api/player-dashboard.models';

// Test-only builders shared by the dashboard's specs and its two host pages'
// specs. Not imported by any production code.

const KIND: Partial<Record<DashboardMetricKey, DashboardMetricKind>> = {
  points_scored: 'average',
  points_lost: 'average',
  scored_lost_ratio: 'ratio',
  match_points_saved: 'average',
  avg_points_for: 'average',
  avg_points_against: 'average',
  avg_win_margin: 'average',
  avg_loss_margin: 'average',
  winners_per_match: 'average',
  errors_per_match: 'average',
  winner_error_ratio: 'ratio',
};

const LOWER_IS_BETTER: DashboardMetricKey[] = [
  'points_lost',
  'avg_points_against',
  'avg_loss_margin',
  'errors_per_match',
  'error_share_of_lost',
];

export function metricFixture(
  key: DashboardMetricKey,
  overrides: Partial<DashboardMetric> = {},
): DashboardMetric {
  return {
    key,
    kind: KIND[key] ?? 'rate',
    better_when:
      key === 'match_points_saved' ? null : LOWER_IS_BETTER.includes(key) ? 'lower' : 'higher',
    all: { value: 0.5, numerator: 50, denominator: 100, matches_used: 8 },
    recent: null,
    verdict: null,
    ...overrides,
  };
}

export function dashboardFixture(
  overrides: Partial<MemberMatchDashboardResponse> = {},
  metricOverrides: Partial<Record<DashboardMetricKey, Partial<DashboardMetric>>> = {},
): MemberMatchDashboardResponse {
  return {
    total_matches: 12,
    recent_window: 10,
    has_comparison: true,
    metrics: DASHBOARD_METRIC_KEYS.map((key) => metricFixture(key, metricOverrides[key])),
    trends: [],
    landing: null,
    error_breakdown: null,
    ...overrides,
  };
}

export const EMPTY_DASHBOARD: MemberMatchDashboardResponse = {
  total_matches: 0,
  recent_window: 10,
  has_comparison: false,
  metrics: [],
  trends: [],
  landing: null,
  error_breakdown: null,
};
