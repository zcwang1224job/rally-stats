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
  it('shows one empty state, not eighteen blank cards (FR-024)', () => {
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
  it('puts all eighteen metrics into three groups, first group open (FR-007)', () => {
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
    expect(root.querySelectorAll('[data-metric]').length).toBe(18);
    expect(Array.from(root.querySelectorAll('details')).map((d) => (d as HTMLDetailsElement).open)).toEqual([
      true,
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
    const [all, recent] = Array.from(root.querySelectorAll<HTMLButtonElement>('.landing-range__button'));
    expect(all.getAttribute('aria-pressed')).toBe('true');

    recent.click();
    fixture.detectChanges();

    expect(recent.getAttribute('aria-pressed')).toBe('true');
    expect(root.querySelectorAll('.court-marker--scored').length).toBe(2);
    expect(root.querySelectorAll('.court-marker--lost').length).toBe(0);
    expect(fixture.componentInstance.landingView()?.scoredTotal).toBe(3);
    expect(fixture.componentInstance.landingMatchTotal()).toBe(10);
  });

  it('offers no range switch when there is nothing to compare with', () => {
    const root: HTMLElement = setup(
      dashboardFixture({ landing: landing(5, 3, 5), has_comparison: false, total_matches: 6 }),
    ).nativeElement;

    expect(root.querySelector('.landing-range')).toBeNull();
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
