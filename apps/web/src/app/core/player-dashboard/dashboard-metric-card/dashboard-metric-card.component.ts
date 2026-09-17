import { Component, computed, input, output } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { DashboardMetric, DashboardVerdict } from '../../api/player-dashboard.models';
import { formatDelta, formatMetric } from '../dashboard-format';

// Shape carries the verdict, colour only reinforces it (Constitution VII).
const VERDICT_ICON: Record<DashboardVerdict, string> = {
  improved: '▲',
  declined: '▼',
  unchanged: '＝',
  insufficient: '…',
};

/** 034 US2/US3: one metric as a stat tile — label, value, the fraction
 * behind it, how many matches it is based on, and (past ten matches) the
 * last ten compared with everything. **Purely presentational**: whether a
 * change counts as progress arrives as `verdict`, decided on the backend
 * where "lower is better" is known; this never compares two numbers to
 * judge anything itself. */
@Component({
  selector: 'app-dashboard-metric-card',
  imports: [TranslatePipe],
  templateUrl: './dashboard-metric-card.component.html',
  styleUrl: './dashboard-metric-card.component.scss',
})
export class DashboardMetricCardComponent {
  readonly metric = input.required<DashboardMetric>();
  readonly totalMatches = input.required<number>();
  readonly trendSelected = input(false);
  readonly trendToggle = output<void>();

  readonly labelKey = computed(() => `playerDashboard.metric.${this.metric().key}.label`);
  readonly hintKey = computed(() => `playerDashboard.metric.${this.metric().key}.hint`);
  readonly emptyKey = computed(() => `playerDashboard.metric.${this.metric().key}.empty`);

  readonly value = computed(() => {
    const all = this.metric().all;
    return all ? formatMetric(this.metric().kind, all) : null;
  });

  readonly recentValue = computed(() => {
    const recent = this.metric().recent;
    return recent ? formatMetric(this.metric().kind, recent) : null;
  });

  readonly delta = computed(() => {
    const { kind, all, recent } = this.metric();
    return formatDelta(kind, recent?.value ?? null, all?.value ?? null);
  });

  readonly deltaKey = computed(() =>
    this.metric().kind === 'rate' ? 'playerDashboard.delta.points' : 'playerDashboard.delta.plain',
  );

  /** An average's fraction reads "total over N matches", not "a/b". */
  readonly isPerMatch = computed(() => this.metric().kind === 'average');

  verdictIcon(verdict: DashboardVerdict): string {
    return VERDICT_ICON[verdict];
  }
}
