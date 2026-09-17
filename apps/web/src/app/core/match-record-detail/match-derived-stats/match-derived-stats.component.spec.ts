import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import {
  MatchRecordDetailResponse,
  MomentumStats,
  PlayerLandingDistribution,
  ServeStats,
  TempoStats,
} from '../../api/group-member-view.models';
import { MatchDerivedStatsComponent } from './match-derived-stats.component';

// No translations are loaded, so every string renders as its own i18n key —
// assertions below match on keys, never on Chinese/English copy.

const noData: MatchRecordDetailResponse = {
  match_id: 'm1',
  round_number: 1,
  team_a: [
    { roster_entry_id: 'a1', nickname: '甲', team: 'A' },
    { roster_entry_id: 'a2', nickname: '乙', team: 'A' },
  ],
  team_b: [
    { roster_entry_id: 'b1', nickname: '丙', team: 'B' },
    { roster_entry_id: 'b2', nickname: '丁', team: 'B' },
  ],
  score_a: 21,
  score_b: 15,
  winner_team: 'A',
  started_at: '2026-01-01T10:00:00Z',
  ended_at: '2026-01-01T10:20:00Z',
  record_completeness: 'complete',
  events: [],
  player_stats: [],
  serve_stats: null,
  momentum_stats: null,
  tempo_stats: null,
  landing_distribution: [],
};

const doublesServe: ServeStats = {
  teams: [
    { team: 'A', serve_points_won: 12, serve_points_total: 19, receive_points_won: 9, receive_points_total: 16 },
    { team: 'B', serve_points_won: 7, serve_points_total: 16, receive_points_won: 7, receive_points_total: 19 },
  ],
  players: [
    { roster_entry_id: 'a1', nickname: '甲', team: 'A', serve_points_won: 7, serve_points_total: 10, receive_points_won: 5, receive_points_total: 8 },
    { roster_entry_id: 'a2', nickname: '乙', team: 'A', serve_points_won: 5, serve_points_total: 9, receive_points_won: 4, receive_points_total: 8 },
    { roster_entry_id: 'b1', nickname: '丙', team: 'B', serve_points_won: 7, serve_points_total: 16, receive_points_won: 7, receive_points_total: 19 },
    { roster_entry_id: 'b2', nickname: '丁', team: 'B', serve_points_won: 0, serve_points_total: 0, receive_points_won: 0, receive_points_total: 0 },
  ],
  excluded_points: 1,
};

const momentum: MomentumStats = {
  longest_runs: [
    { team: 'A', length: 5, start_score_a: 8, start_score_b: 9, end_score_a: 13, end_score_b: 9 },
    { team: 'B', length: 0, start_score_a: null, start_score_b: null, end_score_a: null, end_score_b: null },
  ],
  max_leads: [
    { team: 'A', margin: 6, score_a: 21, score_b: 15 },
    { team: 'B', margin: 0, score_a: null, score_b: null },
  ],
  lead_changes: [
    { new_leader: 'B', score_a: 2, score_b: 3 },
    { new_leader: 'A', score_a: 10, score_b: 9 },
  ],
};

const tempo: TempoStats = {
  average_seconds: 24.6,
  counted_points: 33,
  longest: { seconds: 71.2, score_a: 14, score_b: 12 },
};

const landing: PlayerLandingDistribution[] = [
  { roster_entry_id: 'a1', nickname: '甲', team: 'A', scored: [], scored_total: 0, lost: [], lost_total: 0 },
  {
    roster_entry_id: 'a2',
    nickname: '乙',
    team: 'A',
    scored: [
      { x: 0.8, y: 0.2 },
      { x: 1.04, y: 0.5 },
    ],
    scored_total: 3,
    lost: [{ x: 0.1, y: 0.9 }],
    lost_total: 1,
  },
  { roster_entry_id: 'b1', nickname: '丙', team: 'B', scored: [{ x: 0.2, y: 0.3 }], scored_total: 1, lost: [], lost_total: 2 },
  { roster_entry_id: 'b2', nickname: '丁', team: 'B', scored: [], scored_total: 0, lost: [], lost_total: 0 },
];

function setup(overrides: Partial<MatchRecordDetailResponse> = {}) {
  TestBed.configureTestingModule({
    imports: [MatchDerivedStatsComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(MatchDerivedStatsComponent);
  fixture.componentRef.setInput('detail', { ...noData, ...overrides });
  fixture.detectChanges();
  return fixture;
}

function section(root: HTMLElement, name: string): HTMLElement {
  return root.querySelector(`[data-section="${name}"]`)!;
}

describe('MatchDerivedStatsComponent — layout (FR-003/FR-009)', () => {
  it('renders four collapsible sections, all collapsed by default', () => {
    const root: HTMLElement = setup().nativeElement;

    const sections = Array.from(root.querySelectorAll('details'));
    expect(sections.map((s) => s.dataset['section'])).toEqual(['serve', 'momentum', 'tempo', 'landing']);
    expect(sections.map((s) => s.open)).toEqual([false, false, false, false]);
  });

  it('shows an independent no-data notice per section, and no numbers', () => {
    const root: HTMLElement = setup().nativeElement;

    for (const name of ['serve', 'momentum', 'tempo', 'landing']) {
      expect(section(root, name).textContent).toContain(`matchRecordDetail.derived.${name}.empty`);
    }
    expect(root.querySelector('table')).toBeNull();
    expect(root.querySelector('app-court-diagram')).toBeNull();
    expect(root.textContent).not.toContain('%');
  });

  it('treats a response from an older backend (new fields absent) as no data', () => {
    const { serve_stats, momentum_stats, tempo_stats, landing_distribution, ...older } = noData;
    void [serve_stats, momentum_stats, tempo_stats, landing_distribution];
    TestBed.configureTestingModule({
      imports: [MatchDerivedStatsComponent],
      providers: [provideTranslateService({})],
    });
    const fixture = TestBed.createComponent(MatchDerivedStatsComponent);
    fixture.componentRef.setInput('detail', older);

    expect(() => fixture.detectChanges()).not.toThrow();
    expect(section(fixture.nativeElement, 'landing').textContent).toContain('landing.empty');
  });

  it('one section having data does not hide the notices of the others', () => {
    const root: HTMLElement = setup({ momentum_stats: momentum }).nativeElement;

    expect(section(root, 'momentum').textContent).not.toContain('momentum.empty');
    expect(section(root, 'serve').textContent).toContain('serve.empty');
    expect(section(root, 'tempo').textContent).toContain('tempo.empty');
  });
});

describe('MatchDerivedStatsComponent — serve stats (US1)', () => {
  it('shows counts and percentage for both teams', () => {
    const root = section(setup({ serve_stats: doublesServe }).nativeElement, 'serve');

    const rows = root.querySelectorAll('[data-table="teams"] tbody tr');
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain('12/19');
    expect(rows[0].textContent).toContain('63%');
    expect(rows[0].textContent).toContain('9/16');
    expect(rows[0].textContent).toContain('56%');
  });

  it('lists every doubles player, and renders a zero total as "—" rather than 0%', () => {
    const root = section(setup({ serve_stats: doublesServe }).nativeElement, 'serve');

    const rows = root.querySelectorAll('[data-table="players"] tbody tr');
    expect(rows.length).toBe(4);
    expect(rows[3].textContent).toContain('丁');
    expect(rows[3].textContent).toContain('0/0');
    expect(rows[3].textContent).toContain('—');
    expect(rows[3].textContent).not.toContain('%');
  });

  it('omits the player table for singles (players is empty)', () => {
    const root = section(
      setup({ serve_stats: { ...doublesServe, players: [] } }).nativeElement,
      'serve',
    );

    expect(root.querySelector('[data-table="teams"]')).not.toBeNull();
    expect(root.querySelector('[data-table="players"]')).toBeNull();
  });

  it('explains the excluded points', () => {
    const root = section(setup({ serve_stats: doublesServe }).nativeElement, 'serve');

    expect(root.textContent).toContain('matchRecordDetail.derived.serve.excludedNote');
  });

  it('colors each team row’s label to match that team (scoreboard-style header)', () => {
    const root = section(setup({ serve_stats: doublesServe }).nativeElement, 'serve');

    const rows = root.querySelectorAll('[data-table="teams"] tbody tr');
    expect(rows[0].querySelector('.team-label--a')).not.toBeNull();
    expect(rows[1].querySelector('.team-label--b')).not.toBeNull();
  });
});

describe('MatchDerivedStatsComponent — momentum (US2)', () => {
  it('shows each team’s longest run and max lead, with a distinct wording for zero', () => {
    const root = section(setup({ momentum_stats: momentum }).nativeElement, 'momentum');

    expect(root.textContent).toContain('matchRecordDetail.derived.momentum.runValue');
    expect(root.textContent).toContain('matchRecordDetail.derived.momentum.runNone');
    expect(root.textContent).toContain('matchRecordDetail.derived.momentum.leadValue');
    expect(root.textContent).toContain('matchRecordDetail.derived.momentum.leadNone');
  });

  it('lists every lead change in order', () => {
    const root = section(setup({ momentum_stats: momentum }).nativeElement, 'momentum');

    const items = root.querySelectorAll('.lead-change-list li');
    expect(items.length).toBe(2);
    expect(items[0].textContent).toContain('leadChangeToB');
    expect(items[1].textContent).toContain('leadChangeToA');
  });

  it('renders no list at all when the lead never changed hands', () => {
    const root = section(
      setup({ momentum_stats: { ...momentum, lead_changes: [] } }).nativeElement,
      'momentum',
    );

    expect(root.querySelector('.lead-change-list')).toBeNull();
    expect(root.textContent).toContain('matchRecordDetail.derived.momentum.leadChangesCount');
  });
});

describe('MatchDerivedStatsComponent — tempo (US3)', () => {
  it('shows the average, the longest point, and always the estimate disclaimer', () => {
    const fixture = setup({ tempo_stats: tempo });
    const root = section(fixture.nativeElement, 'tempo');

    expect(root.textContent).toContain('matchRecordDetail.derived.tempo.average');
    expect(root.textContent).toContain('matchRecordDetail.derived.tempo.longest');
    expect(root.textContent).toContain('matchRecordDetail.derived.tempo.estimateNote');
  });

  it('formats under a minute as seconds, and a minute or more as minutes + seconds', () => {
    const component = setup({ tempo_stats: tempo }).componentInstance;

    expect(component.duration(24.6)).toEqual({
      key: 'matchRecordDetail.derived.tempo.seconds',
      params: { seconds: 24.6 },
    });
    expect(component.duration(71.2)).toEqual({
      key: 'matchRecordDetail.derived.tempo.minutesSeconds',
      params: { minutes: 1, seconds: 11 },
    });
  });
});

describe('MatchDerivedStatsComponent — landing distribution (US4)', () => {
  it('defaults to the first player who has anything plotted', () => {
    const fixture = setup({ landing_distribution: landing });

    expect(fixture.componentInstance.selectedPlayer()?.roster_entry_id).toBe('a2');
    const pressed = section(fixture.nativeElement, 'landing').querySelector('[aria-pressed="true"]');
    expect(pressed?.textContent).toContain('乙');
  });

  it('plots the selected player’s scored and lost points, out-of-bounds included', () => {
    const fixture = setup({ landing_distribution: landing });

    expect(fixture.componentInstance.markers()).toEqual([
      { x: 0.8, y: 0.2, kind: 'scored' },
      { x: 1.04, y: 0.5, kind: 'scored' },
      { x: 0.1, y: 0.9, kind: 'lost' },
    ]);
    const root = section(fixture.nativeElement, 'landing');
    expect(root.querySelectorAll('.court-marker').length).toBe(3);
  });

  it('switching player replaces the markers', () => {
    const fixture = setup({ landing_distribution: landing });

    fixture.componentInstance.selectPlayer('b1');
    fixture.detectChanges();

    expect(fixture.componentInstance.markers()).toEqual([{ x: 0.2, y: 0.3, kind: 'scored' }]);
  });

  it('each toggle filters its own kind only', () => {
    const fixture = setup({ landing_distribution: landing });

    fixture.componentInstance.showScored.set(false);
    expect(fixture.componentInstance.markers().map((m) => m.kind)).toEqual(['lost']);

    fixture.componentInstance.showScored.set(true);
    fixture.componentInstance.showLost.set(false);
    expect(fixture.componentInstance.markers().map((m) => m.kind)).toEqual(['scored', 'scored']);
  });

  it('shows how many of the player’s points are actually plotted, and a shape legend', () => {
    const root = section(setup({ landing_distribution: landing }).nativeElement, 'landing');

    expect(root.textContent).toContain('matchRecordDetail.derived.landing.coverageScored');
    expect(root.textContent).toContain('matchRecordDetail.derived.landing.coverageLost');
    expect(root.textContent).toContain('matchRecordDetail.derived.landing.legendScored');
    expect(root.textContent).toContain('matchRecordDetail.derived.landing.legendLost');
  });

  it('shows a per-player notice, not an empty court, for a player with nothing plotted', () => {
    const fixture = setup({ landing_distribution: landing });

    fixture.componentInstance.selectPlayer('b2');
    fixture.detectChanges();

    const root = section(fixture.nativeElement, 'landing');
    expect(root.textContent).toContain('matchRecordDetail.derived.landing.playerEmpty');
    expect(root.querySelector('app-court-diagram')).toBeNull();
  });

  it('falls back to the default player when the detail changes to another match', () => {
    const fixture = setup({ landing_distribution: landing });
    fixture.componentInstance.selectPlayer('b1');

    fixture.componentRef.setInput('detail', {
      ...noData,
      landing_distribution: [
        { roster_entry_id: 'x1', nickname: '戊', team: 'A', scored: [{ x: 0.5, y: 0.5 }], scored_total: 1, lost: [], lost_total: 0 },
      ],
    });
    fixture.detectChanges();

    expect(fixture.componentInstance.selectedPlayer()?.roster_entry_id).toBe('x1');
  });
});
