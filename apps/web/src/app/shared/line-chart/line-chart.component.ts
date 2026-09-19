import { formatPercent } from '../../core/match-record-detail/ratio-format';
import { Component, computed, input, signal } from '@angular/core';

/** One point on the line. `display` is the value as the reader sees it
 * ("60%", "2.0"); `detail` is optional supporting text ("30/50"). A null
 * value is a gap in the line, never a drop to zero. */
export interface LineChartPoint {
  label: string;
  value: number | null;
  display: string;
  detail?: string;
}

/** `rate`: values are 0–1 fractions, axis labels read as percentages. */
export type LineChartKind = 'rate' | 'number';

interface PlottedPoint {
  index: number;
  x: number;
  y: number;
  point: LineChartPoint;
}

// A real aspect ratio (not `preserveAspectRatio="none"`): markers stay round
// at every width.
const WIDTH = 320;
const HEIGHT = 120;
const PAD_X = 8;
const PAD_Y = 12;

/** The app's single-series line chart (the player dashboard's metric trends,
 * the match history's per-round win rate). One 2px line in the neutral
 * series colour on hairline gridlines, labelled axis bounds, and three ways
 * to read it that don't depend on each other: the newest point is read out
 * below the plot; hovering / arrow keys move a crosshair and the readout;
 * and the table view lists every point. */
@Component({
  selector: 'app-line-chart',
  templateUrl: './line-chart.component.html',
  styleUrl: './line-chart.component.scss',
})
export class LineChartComponent {
  readonly points = input.required<LineChartPoint[]>();
  readonly kind = input<LineChartKind>('number');
  /** Visible title above the plot; omit when the surrounding section's
   * heading already names the chart. */
  readonly caption = input<string | null>(null);
  /** Screen-reader summary of the whole line. */
  readonly ariaLabel = input.required<string>();
  /** Fixed axis bounds (e.g. 0–1 for a win rate); otherwise the data's. */
  readonly bounds = input<{ min: number; max: number } | null>(null);
  /** Labels under the plot's two ends; default: first/last point labels. */
  readonly startLabel = input<string | null>(null);
  readonly endLabel = input<string | null>(null);
  readonly note = input<string | null>(null);
  readonly tableViewLabel = input.required<string>();
  readonly labelHeader = input.required<string>();
  readonly valueHeader = input.required<string>();

  readonly viewBox = `0 0 ${WIDTH} ${HEIGHT}`;
  readonly width = WIDTH;
  readonly height = HEIGHT;

  private readonly hovered = signal<number | null>(null);

  private readonly range = computed(() => {
    const fixed = this.bounds();
    if (fixed) {
      return fixed;
    }
    const values = this.points()
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
    const points = this.points();
    const { min, max } = this.range();
    const span = max - min || 1;
    const step = points.length > 1 ? (WIDTH - 2 * PAD_X) / (points.length - 1) : 0;
    const x0 = points.length > 1 ? PAD_X : WIDTH / 2;
    return points.flatMap((point, index) =>
      point.value === null
        ? []
        : [
            {
              index,
              x: x0 + step * index,
              y: HEIGHT - PAD_Y - ((point.value - min) / span) * (HEIGHT - 2 * PAD_Y),
              point,
            },
          ],
    );
  });

  /** One polyline per unbroken run of values. */
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

  /** The crosshair's point; the newest one until the reader moves it. */
  readonly active = computed<PlottedPoint | null>(() => {
    const hovered = this.hovered();
    return this.plotted().find((p) => p.index === hovered) ?? this.last();
  });

  readonly axisMax = computed(() => this.formatBound(this.range().max));
  readonly axisMin = computed(() => this.formatBound(this.range().min));
  readonly start = computed(() => this.startLabel() ?? this.points()[0]?.label ?? '');
  readonly end = computed(() => this.endLabel() ?? this.points().at(-1)?.label ?? '');

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
    return this.kind() === 'rate' ? formatPercent(value) : value.toFixed(1);
  }
}
