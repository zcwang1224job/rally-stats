import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import {
  DashboardLanding,
  DashboardLandingPoint,
  MemberMatchDashboardResponse,
} from '../api/player-dashboard.models';
import { EMPTY_DASHBOARD, dashboardFixture } from './dashboard-fixtures';
import { PlayerDashboardComponent } from './player-dashboard.component';

// No translations are loaded, so every string renders as its own i18n key.

function setup(
  dashboard: MemberMatchDashboardResponse | null,
  inputs: { loading?: boolean; failed?: boolean; singlesCourt?: boolean } = {},
): ComponentFixture<PlayerDashboardComponent> {
  TestBed.configureTestingModule({
    imports: [PlayerDashboardComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(PlayerDashboardComponent);
  fixture.componentRef.setInput('dashboard', dashboard);
  for (const [name, value] of Object.entries(inputs)) {
    fixture.componentRef.setInput(name, value);
  }
  fixture.detectChanges();
  return fixture;
}

function group(root: HTMLElement, name: string): HTMLDetailsElement {
  return root.querySelector(`[data-group="${name}"]`)!;
}

function cardKeys(root: HTMLElement, name: string): string[] {
  return Array.from(group(root, name).querySelectorAll('[data-metric]')).map(
    (el) => (el as HTMLElement).dataset['metric']!,
  );
}

function landing(scored: number, lost: number, recentScored: number): DashboardLanding {
  const spots = (count: number): DashboardLandingPoint[] =>
    Array.from({ length: count }, (_, i) => [0.6 + i / 1000, 0.5]);
  return {
    scored: spots(scored),
    lost: spots(lost),
    scored_total: scored + 4,
    lost_total: lost + 2,
    matches_used: 9,
    recent_scored_count: recentScored,
    recent_lost_count: 0,
    recent_scored_total: recentScored + 1,
    recent_lost_total: 1,
    recent_matches_used: 4,
  };
}

describe('PlayerDashboardComponent — states', () => {
  it('shows one empty state, not twenty-three blank cards (FR-024)', () => {
    const root: HTMLElement = setup(EMPTY_DASHBOARD).nativeElement;

    expect(root.querySelector('[data-state="empty"]')?.textContent).toContain('playerDashboard.empty');
    expect(root.querySelector('details')).toBeNull();
    expect(root.querySelector('[data-metric]')).toBeNull();
  });

  it('tells loading from failed while there is no data yet', () => {
    expect(setup(null, { loading: true }).nativeElement.querySelector('[data-state="loading"]')).not.toBeNull();
    TestBed.resetTestingModule();
    const failed: HTMLElement = setup(null, { failed: true }).nativeElement;
    expect(failed.querySelector('[data-state="failed"]')?.getAttribute('role')).toBe('alert');
  });
});

describe('PlayerDashboardComponent — metrics (US2)', () => {
  it('puts all twenty-three metrics into four groups, first group open (FR-007)', () => {
    const root: HTMLElement = setup(dashboardFixture()).nativeElement;

    expect(cardKeys(root, 'serve')).toEqual(['team_serve', 'team_receive', 'own_serve', 'own_receive']);
    expect(cardKeys(root, 'clutch')).toEqual([
      'endgame',
      'deuce',
      'match_point_conversion',
      'match_points_saved',
      'when_leading',
      'when_tied',
      'when_trailing',
    ]);
    expect(cardKeys(root, 'scoring')).toEqual([
      'points_scored',
      'points_lost',
      'scored_lost_ratio',
      'avg_points_for',
      'avg_points_against',
      'avg_win_margin',
      'avg_loss_margin',
    ]);
    // 035: the fourth group, after scoring, in the backend's order.
    expect(cardKeys(root, 'ending')).toEqual([
      'winner_share',
      'winners_per_match',
      'errors_per_match',
      'error_share_of_lost',
      'winner_error_ratio',
    ]);
    expect(Array.from(root.querySelectorAll('details')).map((d) => d.dataset['group'])).toEqual([
      'serve',
      'clutch',
      'scoring',
      'ending',
      'landing',
    ]);
    expect(root.querySelectorAll('[data-metric]').length).toBe(23);
    expect(Array.from(root.querySelectorAll('details')).map((d) => (d as HTMLDetailsElement).open)).toEqual([
      true,
      false,
      false,
      false,
      false,
    ]);
  });

  it('explains the serve exclusions next to the serve metrics (FR-023)', () => {
    const root: HTMLElement = setup(dashboardFixture()).nativeElement;

    expect(group(root, 'serve').textContent).toContain('playerDashboard.serveExclusionNote');
    expect(group(root, 'clutch').textContent).not.toContain('playerDashboard.serveExclusionNote');
  });

  it('skips a metric key it does not know instead of crashing', () => {
    const dashboard = dashboardFixture();
    dashboard.metrics.push({ ...dashboard.metrics[0], key: 'from_the_future' as never });

    expect(() => setup(dashboard)).not.toThrow();
  });
});

describe('PlayerDashboardComponent — trend (US3)', () => {
  const withTrend = dashboardFixture({
    trends: [
      {
        key: 'team_serve',
        points: [
          { from_ended_at: '2026-06-01T12:00:00Z', to_ended_at: '2026-06-05T12:00:00Z', value: 0.4, numerator: 20, denominator: 50 },
          { from_ended_at: '2026-06-02T12:00:00Z', to_ended_at: '2026-06-06T12:00:00Z', value: 0.5, numerator: 25, denominator: 50 },
        ],
      },
    ],
  });

  function trendButton(root: HTMLElement, key: string): HTMLButtonElement {
    return root.querySelector(`[data-metric="${key}"] button`)!;
  }

  it('shows no chart until a metric is picked, then that metric\'s line in its own group', () => {
    const fixture = setup(withTrend);
    const root: HTMLElement = fixture.nativeElement;
    expect(root.querySelector('app-dashboard-trend-chart')).toBeNull();

    trendButton(root, 'team_serve').click();
    fixture.detectChanges();

    expect(group(root, 'serve').querySelector('app-dashboard-trend-chart polyline')).not.toBeNull();
    expect(group(root, 'clutch').querySelector('app-dashboard-trend-chart')).toBeNull();
    expect(trendButton(root, 'team_serve').getAttribute('aria-pressed')).toBe('true');
  });

  it('says there are not enough matches for a metric without a series (FR-029)', () => {
    const fixture = setup(withTrend);
    const root: HTMLElement = fixture.nativeElement;

    trendButton(root, 'endgame').click();
    fixture.detectChanges();

    const chart = group(root, 'clutch').querySelector('app-dashboard-trend-chart')!;
    expect(chart.textContent).toContain('playerDashboard.trend.notEnough');
    expect(chart.querySelector('svg')).toBeNull();
  });

  it('closes the chart when the same metric is picked again', () => {
    const fixture = setup(withTrend);
    const root: HTMLElement = fixture.nativeElement;

    trendButton(root, 'team_serve').click();
    fixture.detectChanges();
    trendButton(root, 'team_serve').click();
    fixture.detectChanges();

    expect(root.querySelector('app-dashboard-trend-chart')).toBeNull();
  });
});

describe('PlayerDashboardComponent — landing (US4)', () => {
  it('shows a notice instead of an empty court when nothing was plotted (FR-034)', () => {
    const root: HTMLElement = setup(dashboardFixture({ landing: null })).nativeElement;

    expect(group(root, 'landing').textContent).toContain('playerDashboard.landing.empty');
    expect(root.querySelector('app-court-diagram')).toBeNull();
  });

  it('plots every landing, says in words which side is mine, and reports coverage', () => {
    const root: HTMLElement = setup(dashboardFixture({ landing: landing(5, 3, 2) })).nativeElement;

    expect(root.querySelectorAll('.court-marker--scored').length).toBe(5);
    expect(root.querySelectorAll('.court-marker--lost').length).toBe(3);
    const sides = root.querySelector('[data-sides]')!.textContent!;
    expect(sides.indexOf('playerDashboard.landing.mySide')).toBeLessThan(
      sides.indexOf('playerDashboard.landing.opponentSide'),
    );
    expect(root.querySelector('[data-coverage="scored"]')?.textContent).toContain(
      'playerDashboard.landing.coverageScored',
    );
    expect(group(root, 'landing').textContent).toContain('playerDashboard.landing.legendScored');
  });

  it('switches to the recent range by taking the prefix of each array', () => {
    const fixture = setup(dashboardFixture({ landing: landing(5, 3, 2) }));
    const root: HTMLElement = fixture.nativeElement;
    const [all, recent] = Array.from(root.querySelectorAll<HTMLButtonElement>('.dashboard-range__button'));
    expect(all.getAttribute('aria-pressed')).toBe('true');

    recent.click();
    fixture.detectChanges();

    expect(recent.getAttribute('aria-pressed')).toBe('true');
    expect(root.querySelectorAll('.court-marker--scored').length).toBe(2);
    expect(root.querySelectorAll('.court-marker--lost').length).toBe(0);
    expect(fixture.componentInstance.landingView()?.scoredTotal).toBe(3);
    expect(fixture.componentInstance.rangeMatchTotal()).toBe(10);
  });

  it('offers no range switch when there is nothing to compare with', () => {
    const root: HTMLElement = setup(
      dashboardFixture({ landing: landing(5, 3, 5), has_comparison: false, total_matches: 6 }),
    ).nativeElement;

    expect(root.querySelector('.dashboard-range')).toBeNull();
    expect(root.querySelectorAll('.court-marker--scored').length).toBe(5);
  });

  it('hides each kind independently', () => {
    const fixture = setup(dashboardFixture({ landing: landing(5, 3, 2) }));
    const root: HTMLElement = fixture.nativeElement;
    const [scoredToggle] = Array.from(root.querySelectorAll<HTMLInputElement>('.landing-toggles input'));

    scoredToggle.checked = false;
    scoredToggle.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    expect(root.querySelectorAll('.court-marker--scored').length).toBe(0);
    expect(root.querySelectorAll('.court-marker--lost').length).toBe(3);
  });

  it('turns dense only past 150 markers, keeping both shapes', () => {
    const sparse: HTMLElement = setup(dashboardFixture({ landing: landing(100, 50, 2) })).nativeElement;
    expect(sparse.querySelector('app-court-diagram')?.classList.contains('court--dense')).toBe(false);

    TestBed.resetTestingModule();
    const dense: HTMLElement = setup(dashboardFixture({ landing: landing(100, 51, 2) })).nativeElement;
    expect(dense.querySelector('app-court-diagram')?.classList.contains('court--dense')).toBe(true);
    expect(dense.querySelectorAll('.court-marker--lost').length).toBe(51);
  });

  it('draws singles lines only when the host page says the matches are singles', () => {
    const doubles: HTMLElement = setup(dashboardFixture({ landing: landing(2, 1, 1) })).nativeElement;
    expect(doubles.querySelector('.out-of-play-band')).toBeNull();

    TestBed.resetTestingModule();
    const singles: HTMLElement = setup(dashboardFixture({ landing: landing(2, 1, 1) }), {
      singlesCourt: true,
    }).nativeElement;
    expect(singles.querySelectorAll('.out-of-play-band').length).toBe(2);
  });
});

describe('PlayerDashboardComponent — winners & errors (035 US3)', () => {
  const breakdown = {
    all: { out: 6, net: 3, serve_fault: 1, other_error: 0 },
    recent: { out: 1, net: 3, serve_fault: 0, other_error: 0 },
  };

  function rows(root: HTMLElement): { kind: string; count: string; percent: string }[] {
    return Array.from(root.querySelectorAll<HTMLTableRowElement>('[data-error-breakdown] tr')).map(
      (tr) => ({
        kind: tr.dataset['errorKind']!,
        count: tr.querySelector('.error-breakdown__count')!.textContent!.trim(),
        percent: tr.querySelector('.error-breakdown__percent')!.textContent!.trim(),
      }),
    );
  }

  it('lists the four error kinds in a fixed order with count and share, under the ending cards', () => {
    const root: HTMLElement = setup(dashboardFixture({ error_breakdown: breakdown })).nativeElement;

    const ending = group(root, 'ending');
    expect(ending.querySelector('[data-error-breakdown]')).not.toBeNull();
    expect(rows(root)).toEqual([
      { kind: 'out', count: '6', percent: '60%' },
      { kind: 'net', count: '3', percent: '30%' },
      { kind: 'serve_fault', count: '1', percent: '10%' },
      { kind: 'other_error', count: '0', percent: '0%' },
    ]);
    expect(ending.querySelector('[data-error-breakdown-total]')?.textContent).toContain(
      'playerDashboard.errorBreakdown.total',
    );
    // The breakdown sits below the cards, not among them.
    const cards = ending.querySelector('.dashboard-group__cards')!;
    const table = ending.querySelector('[data-error-breakdown]')!;
    expect(cards.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows one notice instead of four zero rows when no error was ever recorded', () => {
    const root: HTMLElement = setup(dashboardFixture({ error_breakdown: null })).nativeElement;

    expect(group(root, 'ending').querySelector('[data-error-breakdown]')).toBeNull();
    expect(group(root, 'ending').querySelector('[data-state="error-breakdown-empty"]')?.textContent).toContain(
      'playerDashboard.errorBreakdown.empty',
    );
    expect(cardKeys(root, 'ending').length).toBe(5); // the cards are still there
  });

  it('has exactly one range switch, above the groups, and none inside the landing group', () => {
    const root: HTMLElement = setup(
      dashboardFixture({ landing: landing(5, 3, 2), error_breakdown: breakdown }),
    ).nativeElement;

    expect(root.querySelectorAll('.dashboard-range').length).toBe(1);
    expect(root.querySelectorAll('.dashboard-range__button').length).toBe(2);
    expect(group(root, 'landing').querySelector('.dashboard-range')).toBeNull();
    expect(root.querySelector('.landing-range')).toBeNull();
    const range = root.querySelector('.dashboard-range')!;
    const firstGroup = root.querySelector('details')!;
    expect(range.compareDocumentPosition(firstGroup) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Still only the first group open.
    expect(Array.from(root.querySelectorAll('details')).map((d) => (d as HTMLDetailsElement).open)).toEqual([
      true,
      false,
      false,
      false,
      false,
    ]);
  });

  it('one switch changes the landing markers and the error breakdown together', () => {
    const fixture = setup(dashboardFixture({ landing: landing(5, 3, 2), error_breakdown: breakdown }));
    const root: HTMLElement = fixture.nativeElement;
    expect(root.querySelectorAll('.court-marker--scored').length).toBe(5);
    expect(rows(root)[0]).toEqual({ kind: 'out', count: '6', percent: '60%' });

    const [, recent] = Array.from(root.querySelectorAll<HTMLButtonElement>('.dashboard-range__button'));
    recent.click();
    fixture.detectChanges();

    expect(root.querySelectorAll('.court-marker--scored').length).toBe(2);
    expect(rows(root)[0]).toEqual({ kind: 'out', count: '1', percent: '25%' });
    expect(rows(root)[1]).toEqual({ kind: 'net', count: '3', percent: '75%' });
    expect(fixture.componentInstance.errorBreakdownView()?.total).toBe(4);
  });

  it('opens the two blocks it drives, so the press is never invisible', () => {
    const fixture = setup(dashboardFixture({ landing: landing(5, 3, 2), error_breakdown: breakdown }));
    const root: HTMLElement = fixture.nativeElement;
    const scrolled: HTMLElement[] = [];
    for (const el of Array.from(root.querySelectorAll<HTMLElement>('*'))) {
      el.scrollIntoView = () => scrolled.push(el);
    }
    expect(group(root, 'ending').open).toBe(false);
    expect(group(root, 'landing').open).toBe(false);

    const [all, recent] = Array.from(root.querySelectorAll<HTMLButtonElement>('.dashboard-range__button'));
    recent.click();
    fixture.detectChanges();

    expect(group(root, 'ending').open).toBe(true);
    expect(group(root, 'landing').open).toBe(true);
    expect(scrolled.pop()?.classList.contains('error-breakdown__title')).toBe(true);

    // Going back does the same, so neither chip is the silent one.
    group(root, 'ending').open = false;
    all.click();
    fixture.detectChanges();
    expect(group(root, 'ending').open).toBe(true);
  });

  it('shows the whole range when there is nothing to compare, even if recent is present', () => {
    const root: HTMLElement = setup(
      dashboardFixture({ error_breakdown: { ...breakdown, recent: null }, has_comparison: false, total_matches: 6 }),
    ).nativeElement;

    expect(root.querySelector('.dashboard-range')).toBeNull();
    expect(rows(root)[0]).toEqual({ kind: 'out', count: '6', percent: '60%' });
  });
});

describe('PlayerDashboardComponent — focusMetric (036 FR-010)', () => {
  it('gives every metric card an anchor', () => {
    const root: HTMLElement = setup(dashboardFixture()).nativeElement;
    const card = root.querySelector<HTMLElement>('#metric-endgame')!;
    expect(card.dataset['metric']).toBe('endgame');
    expect(card.getAttribute('tabindex')).toBe('-1');
  });

  it('opens the collapsed group the metric lives in and moves focus to its card', () => {
    const fixture = setup(dashboardFixture());
    const root: HTMLElement = fixture.nativeElement;
    document.body.appendChild(root); // focus() needs an attached element
    expect(group(root, 'ending').open).toBe(false);

    fixture.componentInstance.focusMetric('winner_share');

    expect(group(root, 'ending').open).toBe(true);
    expect(document.activeElement).toBe(root.querySelector('#metric-winner_share'));
    expect(group(root, 'clutch').open).toBe(false); // only the one it needs
    root.remove();
  });

  it('ignores a key it cannot find rather than throwing', () => {
    const fixture = setup(EMPTY_DASHBOARD);
    expect(() => fixture.componentInstance.focusMetric('team_serve')).not.toThrow();
  });
});
