import { formatPercent } from '../../../../core/match-record-detail/ratio-format';
import { Component, input, output } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import {
  BenchmarkGroupOption,
  GroupBenchmarkMetric,
  GroupBenchmarkResponse,
} from '../../../../core/api/group-benchmark.models';
import { formatMetric } from '../../../../core/player-dashboard/dashboard-format';

/** 036 US3: each of my dashboard metrics next to the group's average and my
 * rank among the players who have enough matches. **Purely presentational**:
 * who is compared, the five-match and three-player minimums, the ranking
 * direction and the four statuses are all decided on the backend
 * (`member/group_benchmark.py`).
 *
 * Collapsed by default and silent until opened — it is the most expensive
 * request on the page, so a member who never uses it never pays for it
 * (research.md Decision 9). The page decides when to load; this only says
 * "I was opened" and "another group was chosen". */
@Component({
  selector: 'app-group-benchmark',
  imports: [TranslatePipe],
  templateUrl: './group-benchmark.component.html',
  styleUrl: './group-benchmark.component.scss',
})
export class GroupBenchmarkComponent {
  /** null: not loaded yet. []: I have no group to compare within. */
  readonly groups = input.required<BenchmarkGroupOption[] | null>();
  readonly selectedGroupId = input<string | null>(null);
  readonly benchmark = input<GroupBenchmarkResponse | null>(null);
  readonly loading = input(false);
  readonly failed = input(false);

  readonly opened = output<void>();
  readonly groupChanged = output<string>();

  onToggle(event: Event): void {
    if ((event.target as HTMLDetailsElement).open) {
      this.opened.emit();
    }
  }

  onSelect(event: Event): void {
    this.groupChanged.emit((event.target as HTMLSelectElement).value);
  }

  labelKey(metric: GroupBenchmarkMetric): string {
    return `playerDashboard.metric.${metric.key}.label`;
  }

  mine(metric: GroupBenchmarkMetric): string {
    return metric.mine ? formatMetric(metric.kind, metric.mine) : '—';
  }

  /** The average of several players' values has no numerator/denominator of
   * its own, so it is written from the value alone — same precision as a
   * metric card. */
  average(metric: GroupBenchmarkMetric): string {
    if (metric.group_average === null) {
      return '—';
    }
    return metric.kind === 'rate'
      ? formatPercent(metric.group_average)
      : metric.group_average.toFixed(1);
  }

  groupStatusKey(group: BenchmarkGroupOption): string | null {
    if (group.status === 'disbanded') {
      return 'groupBenchmark.groupStatus.disbanded';
    }
    return group.member_status === 'active'
      ? null
      : `groupBenchmark.groupStatus.${group.member_status}`;
  }
}
