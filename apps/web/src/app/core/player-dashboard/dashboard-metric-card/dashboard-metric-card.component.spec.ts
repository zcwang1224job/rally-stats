import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { DashboardMetric } from '../../api/player-dashboard.models';
import { metricFixture } from '../dashboard-fixtures';
import { DashboardMetricCardComponent } from './dashboard-metric-card.component';

// No translations are loaded, so every string renders as its own i18n key.

function setup(metric: DashboardMetric, totalMatches = 12): ComponentFixture<DashboardMetricCardComponent> {
  TestBed.configureTestingModule({
    imports: [DashboardMetricCardComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(DashboardMetricCardComponent);
  fixture.componentRef.setInput('metric', metric);
  fixture.componentRef.setInput('totalMatches', totalMatches);
  fixture.detectChanges();
  return fixture;
}

function text(root: HTMLElement, selector: string): string {
  return root.querySelector(selector)?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

describe('DashboardMetricCardComponent — value (US2)', () => {
  it('shows a rate as a whole percentage with its fraction and basis', () => {
    const root: HTMLElement = setup(
      metricFixture('team_serve', {
        all: { value: 0.5118, numerator: 389, denominator: 760, matches_used: 31 },
      }),
      42,
    ).nativeElement;

    expect(text(root, 'h4')).toBe('playerDashboard.metric.team_serve.label');
    expect(text(root, '[data-value]')).toBe('51%');
    expect(text(root, '[data-fraction]')).toBe('389/760');
    expect(text(root, '[data-basis]')).toBe('playerDashboard.basedOn');
    expect(root.querySelector('[data-recent]')).toBeNull();
  });

  it('shows an average with one decimal and a per-match fraction', () => {
    const root: HTMLElement = setup(
      metricFixture('avg_loss_margin', {
        all: { value: 6.3913, numerator: 147, denominator: 23, matches_used: 23 },
      }),
    ).nativeElement;

    expect(text(root, '[data-value]')).toBe('6.4');
    expect(text(root, '[data-fraction]')).toBe('playerDashboard.fraction.perMatch');
  });

  it('shows a ratio with one decimal and a plain fraction', () => {
    const root: HTMLElement = setup(
      metricFixture('scored_lost_ratio', {
        all: { value: 1.3521, numerator: 96, denominator: 71, matches_used: 14 },
      }),
    ).nativeElement;

    expect(text(root, '[data-value]')).toBe('1.4');
    expect(text(root, '[data-fraction]')).toBe('96/71');
  });

  it('shows "0/0 —" for a metric that applies but never occurred, never 0% (FR-015)', () => {
    const root: HTMLElement = setup(
      metricFixture('when_trailing', {
        all: { value: null, numerator: 0, denominator: 0, matches_used: 5 },
      }),
    ).nativeElement;

    expect(text(root, '[data-value]')).toBe('—');
    expect(text(root, '[data-fraction]')).toBe('0/0');
    expect(root.textContent).not.toContain('0%');
  });

  it('shows the metric\'s own no-data notice and no numbers when nothing has its data (FR-004)', () => {
    const root: HTMLElement = setup(metricFixture('own_serve', { all: null })).nativeElement;

    expect(text(root, '[data-empty]')).toBe('playerDashboard.metric.own_serve.empty');
    expect(root.querySelector('[data-value]')).toBeNull();
    expect(root.querySelector('button')).toBeNull();
    expect(root.textContent).not.toContain('%');
  });
});

describe('DashboardMetricCardComponent — recent vs all (US3)', () => {
  const recent = { value: 0.561, numerator: 101, denominator: 180, matches_used: 8 };

  it('shows the recent value, its basis, the signed difference and the verdict in words', () => {
    const root: HTMLElement = setup(
      metricFixture('team_serve', {
        all: { value: 0.512, numerator: 389, denominator: 760, matches_used: 31 },
        recent,
        verdict: 'improved',
      }),
    ).nativeElement;

    const block = text(root, '[data-recent]');
    expect(block).toContain('56%');
    expect(block).toContain('playerDashboard.recent.basedOn');
    expect(text(root, '[data-delta]')).toBe('playerDashboard.delta.points');
    const verdict = root.querySelector('[data-verdict="improved"]')!;
    // Words plus a shape — never colour alone (FR-008).
    expect(verdict.textContent).toContain('playerDashboard.verdict.improved');
    expect(verdict.querySelector('[aria-hidden="true"]')?.textContent).toBe('▲');
  });

  it('takes "improved" from the backend even when the number went down (FR-026)', () => {
    const root: HTMLElement = setup(
      metricFixture('avg_loss_margin', {
        all: { value: 6.4, numerator: 147, denominator: 23, matches_used: 23 },
        recent: { value: 3.8, numerator: 19, denominator: 5, matches_used: 5 },
        verdict: 'improved',
      }),
    ).nativeElement;

    expect(root.querySelector('[data-verdict="improved"]')).not.toBeNull();
    expect(text(root, '[data-delta]')).toBe('playerDashboard.delta.plain');
  });

  it.each(['declined', 'unchanged', 'insufficient'] as const)('words the "%s" verdict', (verdict) => {
    const root: HTMLElement = setup(metricFixture('endgame', { recent, verdict })).nativeElement;

    expect(text(root, `[data-verdict="${verdict}"]`)).toContain(`playerDashboard.verdict.${verdict}`);
  });

  it('says "insufficient" even when no recent match has the data at all', () => {
    const root: HTMLElement = setup(
      metricFixture('deuce', { recent: null, verdict: 'insufficient' }),
    ).nativeElement;

    expect(root.querySelector('[data-verdict="insufficient"]')).not.toBeNull();
    expect(root.querySelector('[data-delta]')).toBeNull();
  });

  it('compares a metric without a direction but never judges it', () => {
    const root: HTMLElement = setup(
      metricFixture('match_points_saved', {
        all: { value: 1.5, numerator: 30, denominator: 20, matches_used: 20 },
        recent: { value: 3, numerator: 30, denominator: 10, matches_used: 10 },
        verdict: null,
      }),
    ).nativeElement;

    expect(text(root, '[data-recent]')).toContain('3.0');
    expect(root.querySelector('[data-delta]')).not.toBeNull();
    expect(root.querySelector('[data-verdict]')).toBeNull();
  });

  it('asks for the trend through a pressed-state button', () => {
    const fixture = setup(metricFixture('team_serve'));
    const asked = vi.fn();
    fixture.componentInstance.trendToggle.subscribe(asked);
    const button: HTMLButtonElement = fixture.nativeElement.querySelector('button');

    expect(button.getAttribute('aria-pressed')).toBe('false');
    button.click();
    expect(asked).toHaveBeenCalledTimes(1);

    fixture.componentRef.setInput('trendSelected', true);
    fixture.detectChanges();
    expect(button.getAttribute('aria-pressed')).toBe('true');
  });
});
