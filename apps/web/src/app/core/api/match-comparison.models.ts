import {
  DashboardMetricKey,
  DashboardMetricKind,
  DashboardMetricValue,
} from './player-dashboard.models';

// 036-match-insights-benchmarks US4: a friend's numbers next to mine. Which
// side is "better" arrives decided (`better`) — it depends on each metric's
// direction and on both sides having at least three matches behind the
// number, which is the backend's to know.

export interface ComparisonMetric {
  key: DashboardMetricKey;
  kind: DashboardMetricKind;
  better_when: 'higher' | 'lower' | null;
  friend: DashboardMetricValue | null;
  me: DashboardMetricValue | null;
  better: 'me' | 'friend' | 'tie' | null; // null: nothing can fairly be said
}

/** From MY side: `wins` are mine, `avg_margin` is mine minus theirs. */
export interface HeadToHeadTally {
  matches: number;
  wins: number;
  losses: number;
  win_rate: number;
  avg_margin: number;
}

export interface MatchComparisonResponse {
  friend_total_matches: number;
  my_total_matches: number;
  metrics: ComparisonMetric[]; // all 23, dashboard order, unfiltered
  head_to_head: {
    as_opponents: HeadToHeadTally | null; // null: never played against each other
    as_partners: HeadToHeadTally | null; // null: never partnered
  };
}
