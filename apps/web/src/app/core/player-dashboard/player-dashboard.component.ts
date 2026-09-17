import { Component, computed, input, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import {
  DashboardMetric,
  DashboardMetricKey,
  DashboardTrend,
  MemberMatchDashboardResponse,
} from '../api/player-dashboard.models';
import { CourtDiagramComponent, CourtMarker } from '../court-diagram/court-diagram.component';
import { DashboardMetricCardComponent } from './dashboard-metric-card/dashboard-metric-card.component';
import { DashboardTrendChartComponent } from './dashboard-trend-chart/dashboard-trend-chart.component';

type MetricGroup = 'serve' | 'clutch' | 'scoring';
type LandingRange = 'all' | 'recent';

// Exhaustive on purpose: a metric key added to the models without a home
// here is a compile error, not a card that silently never renders.
const GROUP_OF: Record<DashboardMetricKey, MetricGroup> = {
  team_serve: 'serve',
  team_receive: 'serve',
  own_serve: 'serve',
  own_receive: 'serve',
  endgame: 'clutch',
  deuce: 'clutch',
  match_point_conversion: 'clutch',
  match_points_saved: 'clutch',
  when_leading: 'clutch',
  when_tied: 'clutch',
  when_trailing: 'clutch',
  points_scored: 'scoring',
  points_lost: 'scoring',
  scored_lost_ratio: 'scoring',
  avg_points_for: 'scoring',
  avg_points_against: 'scoring',
  avg_win_margin: 'scoring',
  avg_loss_margin: 'scoring',
};

const GROUPS: MetricGroup[] = ['serve', 'clutch', 'scoring'];

// Past this many markers they overlap too much to count one by one, so the
// court switches to its dense style (research.md Decision 11).
const DENSE_ABOVE = 150;

/** 034-clutch-points-player-dashboard US2-US4: a member's cross-match
 * technique dashboard. Shared by the member's own match history and a
 * friend's records page — same data shape, same component, so the two can
 * never drift apart. **Purely presentational**: every number, including
 * whether a change is progress, arrives computed; the only data work here
 * is slicing the newest-first landing arrays to their recent prefix.
 *
 * Four native `<details>` groups, the first open, so the host page's own
 * content stays within reach on a phone (FR-007). */
@Component({
  selector: 'app-player-dashboard',
  imports: [
    TranslatePipe,
    DashboardMetricCardComponent,
    DashboardTrendChartComponent,
    CourtDiagramComponent,
  ],
  templateUrl: './player-dashboard.component.html',
  styleUrl: './player-dashboard.component.scss',
})
export class PlayerDashboardComponent {
  readonly dashboard = input.required<MemberMatchDashboardResponse | null>();
  readonly loading = input(false);
  readonly failed = input(false);
  /** Draw the landing court with singles lines — only meaningful when the
   * host page has filtered down to singles matches; a mix of singles and
   * doubles has no single right court, so it stays doubles. */
  readonly singlesCourt = input(false);

  readonly groups = GROUPS;

  readonly metricsByGroup = computed<Record<MetricGroup, DashboardMetric[]>>(() => {
    const grouped: Record<MetricGroup, DashboardMetric[]> = { serve: [], clutch: [], scoring: [] };
    for (const metric of this.dashboard()?.metrics ?? []) {
      // `?.`: a key from a newer backend is skipped rather than crashing.
      grouped[GROUP_OF[metric.key]]?.push(metric);
    }
    return grouped;
  });

  // ---- trend (US3)

  private readonly pickedTrendKey = signal<DashboardMetricKey | null>(null);

  /** The pick only counts while that metric is still on the dashboard, so a
   * filter change can't leave a chart for a metric that lost its data. */
  readonly selectedTrendMetric = computed<DashboardMetric | null>(() => {
    const key = this.pickedTrendKey();
    return this.dashboard()?.metrics.find((m) => m.key === key && m.all !== null) ?? null;
  });

  readonly selectedTrend = computed<DashboardTrend | null>(() => {
    const key = this.selectedTrendMetric()?.key;
    return this.dashboard()?.trends.find((trend) => trend.key === key) ?? null;
  });

  toggleTrend(key: DashboardMetricKey): void {
    this.pickedTrendKey.update((current) => (current === key ? null : key));
  }

  trendGroup(): MetricGroup | null {
    const metric = this.selectedTrendMetric();
    return metric ? GROUP_OF[metric.key] : null;
  }

  labelKey(key: DashboardMetricKey): string {
    return `playerDashboard.metric.${key}.label`;
  }

  // ---- landing (US4)

  readonly landingRange = signal<LandingRange>('all');
  readonly showScored = signal(true);
  readonly showLost = signal(true);

  /** "Recent" only exists when there is something to compare with. */
  readonly effectiveRange = computed<LandingRange>(() =>
    this.dashboard()?.has_comparison ? this.landingRange() : 'all',
  );

  readonly landingView = computed(() => {
    const landing = this.dashboard()?.landing;
    if (!landing) {
      return null;
    }
    const recent = this.effectiveRange() === 'recent';
    return {
      scored: recent ? landing.scored.slice(0, landing.recent_scored_count) : landing.scored,
      lost: recent ? landing.lost.slice(0, landing.recent_lost_count) : landing.lost,
      scoredTotal: recent ? landing.recent_scored_total : landing.scored_total,
      lostTotal: recent ? landing.recent_lost_total : landing.lost_total,
      matchesUsed: recent ? landing.recent_matches_used : landing.matches_used,
    };
  });

  readonly markers = computed<CourtMarker[]>(() => {
    const view = this.landingView();
    if (!view) {
      return [];
    }
    return [
      ...(this.showScored() ? view.scored.map(([x, y]) => ({ x, y, kind: 'scored' as const })) : []),
      ...(this.showLost() ? view.lost.map(([x, y]) => ({ x, y, kind: 'lost' as const })) : []),
    ];
  });

  readonly dense = computed(() => this.markers().length > DENSE_ABOVE);

  /** "of M" next to the landing block: the range's own match count. */
  readonly landingMatchTotal = computed(() => {
    const dashboard = this.dashboard();
    if (!dashboard) {
      return 0;
    }
    return this.effectiveRange() === 'recent'
      ? Math.min(dashboard.recent_window, dashboard.total_matches)
      : dashboard.total_matches;
  });
}
