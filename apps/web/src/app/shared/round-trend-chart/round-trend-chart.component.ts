import { formatPercent } from '../../core/match-record-detail/ratio-format';
import { Component, computed, inject, input } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { RoundWinRatePoint } from '../../core/api/group-member-view.models';
import { LineChartComponent, LineChartPoint } from '../line-chart/line-chart.component';

/** Win rate per round (match history, a group's history): the shared line
 * chart on a fixed 0–100% axis, one point per round. Replaces the two copies
 * of a hand-drawn SVG whose `preserveAspectRatio="none"` stretched every dot
 * into an ellipse and which had no axis. */
@Component({
  selector: 'app-round-trend-chart',
  imports: [TranslatePipe, LineChartComponent],
  template: `
    @if (points().length > 0) {
      <app-line-chart
        [points]="points()"
        kind="rate"
        [bounds]="{ min: 0, max: 1 }"
        [ariaLabel]="
          'member.matchHistory.charts.roundTrendSummary'
            | translate
              : {
                  count: points().length,
                  from: points()[0].display,
                  to: points()[points().length - 1].display,
                }
        "
        [tableViewLabel]="'playerDashboard.trend.tableView' | translate"
        [labelHeader]="'member.matchHistory.charts.roundTrendRound' | translate"
        [valueHeader]="'member.matchHistory.stats.winRate' | translate"
      />
    } @else {
      <p class="chart-empty">{{ 'member.matchHistory.charts.roundTrendEmpty' | translate }}</p>
    }
  `,
  styles: `
    :host {
      display: block;
    }

    .chart-empty {
      margin: 0;
      color: var(--color-text-muted);
      font-size: var(--font-size-caption);
    }
  `,
})
export class RoundTrendChartComponent {
  private readonly translate = inject(TranslateService);
  // Round labels are translated here (the chart takes plain strings), so
  // re-derive them whenever the language changes.
  private readonly lang = toSignal(this.translate.onLangChange);

  readonly rounds = input.required<RoundWinRatePoint[]>();

  readonly points = computed<LineChartPoint[]>(() => {
    this.lang();
    return this.rounds().map((round) => ({
      label: this.translate.instant('groupMemberView.standings.roundColumnLabel', {
        round: round.round_number,
      }),
      value: round.win_rate,
      display: formatPercent(round.win_rate),
      detail: `${round.wins}/${round.wins + round.losses}`,
    }));
  });
}
