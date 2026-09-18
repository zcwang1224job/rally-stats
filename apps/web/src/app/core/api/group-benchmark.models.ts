import {
  DashboardInsights,
  DashboardMetricKey,
  DashboardMetricKind,
  DashboardMetricValue,
} from './player-dashboard.models';

// 036-match-insights-benchmarks US3: where I stand among the people I play
// with. ANONYMOUS BY SHAPE — the server sends the group's average, how many
// players it is an average of, and MY rank; nothing here could hold another
// player's name or number (FR-032).

export interface BenchmarkGroupOption {
  group_id: string;
  group_number: number;
  name: string;
  status: string; // the group's own status
  member_status: 'active' | 'left' | 'kicked'; // mine in it
  my_completed_matches: number;
}

export interface BenchmarkGroupsResponse {
  // Most of my matches first: the first one is the default choice.
  groups: BenchmarkGroupOption[];
}

// ok: average and rank. pool_too_small: fewer than 3 players have enough
// matches — no average at all. self_below_minimum: there is an average, but I
// have too few matches here to be ranked. no_direction: the metric has no
// "better", so an average but never a rank.
export type BenchmarkStatus = 'ok' | 'pool_too_small' | 'self_below_minimum' | 'no_direction';

export interface GroupBenchmarkMetric {
  key: DashboardMetricKey;
  kind: DashboardMetricKind;
  better_when: 'higher' | 'lower' | null;
  mine: DashboardMetricValue | null; // over THIS group's matches only
  status: BenchmarkStatus;
  group_average: number | null;
  pool_size: number;
  rank: number | null;
}

export interface GroupBenchmarkResponse {
  group: { group_id: string; name: string };
  total_matches: number; // all of the group's completed matches — the fixed range
  my_matches: number;
  metrics: GroupBenchmarkMetric[]; // all 23, dashboard order
  // My unfiltered summary with the in-group source already merged in by the
  // backend. The page shows this INSTEAD of the dashboard's own insights
  // while no filter is active — it never merges the two itself.
  insights: DashboardInsights;
}
