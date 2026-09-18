import { Component, ElementRef, computed, inject, input, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import {
  DashboardErrorsByType,
  DashboardMetric,
  DashboardMetricKey,
  DashboardTrend,
  MemberMatchDashboardResponse,
} from '../api/player-dashboard.models';
import { CourtDiagramComponent, CourtMarker } from '../court-diagram/court-diagram.component';
import { DashboardMetricCardComponent } from './dashboard-metric-card/dashboard-metric-card.component';
import { DashboardTrendChartComponent } from './dashboard-trend-chart/dashboard-trend-chart.component';

type MetricGroup = 'serve' | 'clutch' | 'scoring' | 'ending';
type Range = 'all' | 'recent';

// 035: the error kinds in their fixed display order (same as the picker).
const ERROR_KINDS: (keyof DashboardErrorsByType)[] = ['out', 'net', 'serve_fault', 'other_error'];

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
  // 035-point-ending-type
  winner_share: 'ending',
  winners_per_match: 'ending',
  errors_per_match: 'ending',
  error_share_of_lost: 'ending',
  winner_error_ratio: 'ending',
};

const GROUPS: MetricGroup[] = ['serve', 'clutch', 'scoring', 'ending'];

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
 * Five native `<details>` groups, the first open, so the host page's own
 * content stays within reach on a phone (FR-007).
 *
 * 035-point-ending-type: one dashboard-level "all / recent N" switch
 * (`range`) drives BOTH the landing map and the error breakdown — the
 * two range-dependent pictures — so they can never show different
 * windows side by side (035 research.md Decision 7). */
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

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  /** 036 FR-010: bring one metric's card into view — open the group it
   * lives in, scroll to it, and move focus there so a keyboard or screen
   * reader user ends up in the same place a sighted one does. An unknown key,
   * or a dashboard that is not rendered yet, is simply ignored. */
  focusMetric(key: DashboardMetricKey): void {
    const root = this.host.nativeElement;
    const group = root.querySelector<HTMLDetailsElement>(
      `details[data-group="${GROUP_OF[key]}"]`,
    );
    const card = root.querySelector<HTMLElement>(`#metric-${key}`);
    if (!group || !card) {
      return;
    }
    group.open = true;
    card.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
    card.focus({ preventScroll: true });
  }

  readonly metricsByGroup = computed<Record<MetricGroup, DashboardMetric[]>>(() => {
    const grouped: Record<MetricGroup, DashboardMetric[]> = {
      serve: [],
      clutch: [],
      scoring: [],
      ending: [],
    };
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

  // ---- range (034 US4 landing, 035 error breakdown)

  readonly range = signal<Range>('all');

  /** "Recent" only exists when there is something to compare with. */
  readonly effectiveRange = computed<Range>(() =>
    this.dashboard()?.has_comparison ? this.range() : 'all',
  );

  /** "of M" next to a range-dependent block: the range's own match count. */
  readonly rangeMatchTotal = computed(() => {
    const dashboard = this.dashboard();
    if (!dashboard) {
      return 0;
    }
    return this.effectiveRange() === 'recent'
      ? Math.min(dashboard.recent_window, dashboard.total_matches)
      : dashboard.total_matches;
  });

  // ---- error breakdown (035 US3)

  /** Four rows in a fixed order, each with its share of the range's own
   * errors; null when nothing was recorded. `recent` is null only when
   * there is no comparison, in which case the range is 'all' anyway. */
  readonly errorBreakdownView = computed(() => {
    const breakdown = this.dashboard()?.error_breakdown;
    if (!breakdown) {
      return null;
    }
    const counts =
      this.effectiveRange() === 'recent' && breakdown.recent ? breakdown.recent : breakdown.all;
    const total = ERROR_KINDS.reduce((sum, kind) => sum + counts[kind], 0);
    return {
      total,
      rows: ERROR_KINDS.map((kind) => ({
        kind,
        count: counts[kind],
        share: total > 0 ? counts[kind] / total : 0,
      })),
    };
  });

  // ---- landing (US4)

  readonly showScored = signal(true);
  readonly showLost = signal(true);

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
}
