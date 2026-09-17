import { DatePipe } from '@angular/common';
import { Component, computed, input, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import {
  DashboardMetricKind,
  DashboardTrend,
  DashboardTrendPoint,
} from '../../api/player-dashboard.models';
import { formatMetric } from '../dashboard-format';

interface PlottedPoint {
  index: number;
  x: number;
  y: number;
  point: DashboardTrendPoint;
}

// A real aspect ratio (not `preserveAspectRatio="none"`): the end marker
// stays a circle at every width.
const WIDTH = 320;
const HEIGHT = 120;
const PAD_X = 8;
const PAD_Y = 12;

/** 034 US3: one metric over time, as a single 2px line — each point is
 * already a five-match moving window computed on the backend, so this only
 * scales and draws. One series, so the title names it and there is no
 * legend. Read three ways, none of which depends on the others: the
 * endpoint is labelled; hovering / arrow keys move a crosshair with a
 * readout below the plot; and the table view lists every point. */
@Component({
  selector: 'app-dashboard-trend-chart',
  imports: [TranslatePipe, DatePipe],
  templateUrl: './dashboard-trend-chart.component.html',
  styleUrl: './dashboard-trend-chart.component.scss',
})
export class DashboardTrendChartComponent {
  /** null: too few matches for this metric to have a trend (FR-029). */
  readonly series = input.required<DashboardTrend | null>();
  readonly kind = input.required<DashboardMetricKind>();
  readonly labelKey = input.required<string>();

  readonly viewBox = `0 0 ${WIDTH} ${HEIGHT}`;
  readonly width = WIDTH;
  readonly height = HEIGHT;

  private readonly hovered = signal<number | null>(null);

  private readonly bounds = computed(() => {
    const values = (this.series()?.points ?? [])
      .map((p) => p.value)
      .filter((v): v is number => v !== null);
    if (values.length === 0) {
      return { min: 0, max: 1 };
    }
    let min = Math.min(...values);
    let max = Math.max(...values);
    if (min === max) {
      // A flat line sits mid-plot instead of on the floor.
      const pad = this.kind() === 'rate' ? 0.05 : 0.5;
      min -= pad;
      max += pad;
    }
    return this.kind() === 'rate'
      ? { min: Math.max(0, min), max: Math.min(1, max) }
      : { min, max };
  });

  readonly plotted = computed<PlottedPoint[]>(() => {
    const points = this.series()?.points ?? [];
    const { min, max } = this.bounds();
    const span = max - min || 1;
    const step = points.length > 1 ? (WIDTH - 2 * PAD_X) / (points.length - 1) : 0;
    return points.flatMap((point, index) =>
      point.value === null
        ? []
        : [
            {
              index,
              x: PAD_X + step * index,
              y: HEIGHT - PAD_Y - ((point.value - min) / span) * (HEIGHT - 2 * PAD_Y),
              point,
            },
          ],
    );
  });

  /** One polyline per unbroken run — a window with no value (its
   * denominator was 0) is a gap, never a line dropped to zero. */
  readonly segments = computed<string[]>(() => {
    const runs: PlottedPoint[][] = [];
    for (const plotted of this.plotted()) {
      const run = runs[runs.length - 1];
      if (run && run[run.length - 1].index === plotted.index - 1) {
        run.push(plotted);
      } else {
        runs.push([plotted]);
      }
    }
    return runs.map((run) => run.map((p) => `${p.x},${p.y}`).join(' '));
  });

  readonly last = computed<PlottedPoint | null>(() => this.plotted().at(-1) ?? null);
  readonly first = computed<PlottedPoint | null>(() => this.plotted()[0] ?? null);

  /** The crosshair's point; the newest one until the reader moves it. */
  readonly active = computed<PlottedPoint | null>(() => {
    const hovered = this.hovered();
    return this.plotted().find((p) => p.index === hovered) ?? this.last();
  });

  readonly axisMax = computed(() => this.formatBound(this.bounds().max));
  readonly axisMin = computed(() => this.formatBound(this.bounds().min));

  format(point: DashboardTrendPoint): string {
    return formatMetric(this.kind(), point);
  }

  /** The pointer only has to be CLOSEST to a point, never on it. */
  onPointerMove(event: PointerEvent): void {
    const plotted = this.plotted();
    const box = (event.currentTarget as SVGElement).getBoundingClientRect();
    if (plotted.length === 0 || box.width === 0) {
      return;
    }
    const x = ((event.clientX - box.left) / box.width) * WIDTH;
    const nearest = plotted.reduce((best, p) => (Math.abs(p.x - x) < Math.abs(best.x - x) ? p : best));
    this.hovered.set(nearest.index);
  }

  onKeydown(event: KeyboardEvent): void {
    const direction = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0;
    const plotted = this.plotted();
    const active = this.active();
    if (direction === 0 || active === null) {
      return;
    }
    event.preventDefault();
    const position = plotted.findIndex((p) => p.index === active.index) + direction;
    this.hovered.set(plotted[Math.min(plotted.length - 1, Math.max(0, position))].index);
  }

  resetHover(): void {
    this.hovered.set(null);
  }

  private formatBound(value: number): string {
    return this.kind() === 'rate' ? `${Math.round(value * 100)}%` : value.toFixed(1);
  }
}
