import { formatDate } from '@angular/common';
import { Component, LOCALE_ID, computed, inject, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import {
  DashboardMetricKind,
  DashboardTrend,
  DashboardTrendPoint,
} from '../../api/player-dashboard.models';
import { LineChartComponent, LineChartPoint } from '../../../shared/line-chart/line-chart.component';
import { formatMetric } from '../dashboard-format';

/** 034 US3: one metric over time. Each point is already a five-match moving
 * window computed on the backend, so this only turns the windows into
 * labelled points for the shared line chart; one series, so the title names
 * it and there is no legend. */
@Component({
  selector: 'app-dashboard-trend-chart',
  imports: [TranslatePipe, LineChartComponent],
  templateUrl: './dashboard-trend-chart.component.html',
  styleUrl: './dashboard-trend-chart.component.scss',
})
export class DashboardTrendChartComponent {
  private readonly locale = inject(LOCALE_ID);

  /** null: too few matches for this metric to have a trend (FR-029). */
  readonly series = input.required<DashboardTrend | null>();
  readonly kind = input.required<DashboardMetricKind>();
  readonly labelKey = input.required<string>();

  readonly points = computed<LineChartPoint[]>(() =>
    (this.series()?.points ?? []).map((point) => ({
      label: `${this.day(point.from_ended_at)}–${this.day(point.to_ended_at)}`,
      value: point.value,
      display: this.format(point),
      detail: `${point.numerator}/${point.denominator}`,
    })),
  );

  readonly first = computed(() => this.points().find((p) => p.value !== null) ?? null);
  readonly last = computed(
    () => [...this.points()].reverse().find((p) => p.value !== null) ?? null,
  );
  readonly startLabel = computed(() => {
    const first = this.series()?.points[0];
    return first ? this.day(first.from_ended_at) : '';
  });
  readonly endLabel = computed(() => {
    const last = this.series()?.points.at(-1);
    return last ? this.day(last.to_ended_at) : '';
  });

  private format(point: DashboardTrendPoint): string {
    return formatMetric(this.kind(), point);
  }

  private day(iso: string): string {
    return formatDate(iso, 'M/d', this.locale);
  }
}
