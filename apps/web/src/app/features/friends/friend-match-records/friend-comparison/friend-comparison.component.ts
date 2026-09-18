import { Component, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import {
  ComparisonMetric,
  HeadToHeadTally,
  MatchComparisonResponse,
} from '../../../../core/api/match-comparison.models';
import { DashboardMetricValue } from '../../../../core/api/player-dashboard.models';
import { NicknameComponent } from '../../../../core/nickname/nickname.component';
import { formatMetric } from '../../../../core/player-dashboard/dashboard-format';

/** 036 US4: each dashboard metric as "friend | me", and our record against
 * and alongside each other. **Purely presentational** — which side is better
 * arrives as `better`; this never compares the two numbers itself. */
@Component({
  selector: 'app-friend-comparison',
  imports: [TranslatePipe, NicknameComponent],
  templateUrl: './friend-comparison.component.html',
  styleUrl: './friend-comparison.component.scss',
})
export class FriendComparisonComponent {
  readonly comparison = input.required<MatchComparisonResponse | null>();
  readonly friendNickname = input<string | null>(null);
  readonly loading = input(false);
  readonly failed = input(false);

  labelKey(metric: ComparisonMetric): string {
    return `playerDashboard.metric.${metric.key}.label`;
  }

  value(metric: ComparisonMetric, side: DashboardMetricValue | null): string {
    return side ? formatMetric(metric.kind, side) : '—';
  }

  /** "+3.5" / "−6.0": the real minus sign, as in the partner/opponent tables. */
  margin(tally: HeadToHeadTally): string {
    const rounded = Math.abs(tally.avg_margin).toFixed(1);
    if (Number(rounded) === 0) {
      return '±0.0';
    }
    return `${tally.avg_margin > 0 ? '+' : '−'}${rounded}`;
  }
}
