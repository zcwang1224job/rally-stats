import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { DashboardTrend, DashboardTrendPoint } from '../../api/player-dashboard.models';
import { DashboardTrendChartComponent } from './dashboard-trend-chart.component';

// No translations are loaded, so every string renders as its own i18n key.

function point(day: number, numerator: number, denominator: number): DashboardTrendPoint {
  const date = (d: number) => `2026-06-${String(d).padStart(2, '0')}T12:00:00Z`;
  return {
    from_ended_at: date(day),
    to_ended_at: date(day + 4),
    value: denominator === 0 ? null : numerator / denominator,
    numerator,
    denominator,
  };
}

const rising: DashboardTrend = {
  key: 'team_serve',
  points: [point(1, 15, 50), point(2, 20, 50), point(3, 25, 50), point(4, 30, 50)],
};

function setup(
  series: DashboardTrend | null,
  kind: 'rate' | 'average' | 'ratio' = 'rate',
): ComponentFixture<DashboardTrendChartComponent> {
  TestBed.configureTestingModule({
    imports: [DashboardTrendChartComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(DashboardTrendChartComponent);
  fixture.componentRef.setInput('series', series);
  fixture.componentRef.setInput('kind', kind);
  fixture.componentRef.setInput('labelKey', 'playerDashboard.metric.team_serve.label');
  fixture.detectChanges();
  return fixture;
}

function readout(root: HTMLElement): string {
  return root.querySelector('[data-readout]')?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

describe('DashboardTrendChartComponent', () => {
  it('says there are not enough matches instead of drawing an empty chart (FR-029)', () => {
    const root: HTMLElement = setup(null).nativeElement;

    expect(root.textContent).toContain('playerDashboard.trend.notEnough');
    expect(root.querySelector('svg')).toBeNull();
  });

  it('draws one line through every point, oldest on the left and rising upward', () => {
    const root: HTMLElement = setup(rising).nativeElement;

    const lines = root.querySelectorAll('polyline');
    expect(lines.length).toBe(1);
    const coordinates = lines[0]
      .getAttribute('points')!
      .split(' ')
      .map((pair) => pair.split(',').map(Number));
    expect(coordinates.length).toBe(4);
    expect(coordinates.map(([x]) => x)).toEqual([...coordinates.map(([x]) => x)].sort((a, b) => a - b));
    // SVG y grows downward: a rising rate means a falling y.
    expect(coordinates[0][1]).toBeGreaterThan(coordinates[3][1]);
  });

  it('labels the axis bounds and reads out the newest point by default', () => {
    const root: HTMLElement = setup(rising).nativeElement;

    expect(root.querySelector('.trend__axis--max')?.textContent).toBe('60%');
    expect(root.querySelector('.trend__axis--min')?.textContent).toBe('30%');
    expect(readout(root)).toContain('60%');
    expect(readout(root)).toContain('30/50');
    expect(root.querySelectorAll('circle').length).toBe(1); // one marker, not a dot per point
  });

  it('breaks the line at a window with no value instead of dropping to zero', () => {
    const gapped: DashboardTrend = {
      key: 'when_trailing',
      points: [point(1, 5, 10), point(2, 6, 10), point(3, 0, 0), point(4, 7, 10), point(5, 8, 10)],
    };
    const root: HTMLElement = setup(gapped).nativeElement;

    const lines = Array.from(root.querySelectorAll('polyline'));
    expect(lines.map((line) => line.getAttribute('points')!.split(' ').length)).toEqual([2, 2]);
  });

  it('moves the crosshair with the arrow keys and gives the value in the readout', () => {
    const fixture = setup(rising);
    const root: HTMLElement = fixture.nativeElement;
    const svg: SVGElement = root.querySelector('svg')!;
    expect(svg.getAttribute('tabindex')).toBe('0');

    svg.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }));
    fixture.detectChanges();
    expect(readout(root)).toContain('50%');

    svg.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }));
    svg.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }));
    svg.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' })); // clamps at the oldest
    fixture.detectChanges();
    expect(readout(root)).toContain('30%');
  });

  it('offers every point in a table, so nothing is reachable by hover alone', () => {
    const root: HTMLElement = setup(rising).nativeElement;

    const rows = Array.from(root.querySelectorAll('.trend__table tbody tr'));
    expect(rows.length).toBe(4);
    expect(rows[0].textContent).toContain('30%');
    expect(rows[0].textContent).toContain('15/50');
    expect(root.querySelector('svg')?.getAttribute('aria-label')).toBe('playerDashboard.trend.summary');
  });

  it('formats an average with one decimal', () => {
    const margins: DashboardTrend = {
      key: 'avg_loss_margin',
      points: [point(1, 60, 5), point(2, 10, 5)],
    };
    const root: HTMLElement = setup(margins, 'average').nativeElement;

    expect(root.querySelector('.trend__axis--max')?.textContent).toBe('12.0');
    expect(readout(root)).toContain('2.0');
  });
});
