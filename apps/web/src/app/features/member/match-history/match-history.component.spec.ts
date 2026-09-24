import { ActivitySummary } from '../../../core/api/sport.models';
import { DashboardSectionsResponse } from '../../../core/api/sports.service';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideTranslateService } from '@ngx-translate/core';
import { MatchRecordDetailDialogComponent } from '../../../core/match-record-detail/match-record-detail-dialog.component';
import { Observable, Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { MemberMatchRecordsResponse } from '../../../core/api/group-member-view.models';
import { InviteCandidatesResponse } from '../../../core/api/friend.models';
import {
  BenchmarkGroupOption,
  BenchmarkGroupsResponse,
  GroupBenchmarkResponse,
} from '../../../core/api/group-benchmark.models';
import { MemberMatchDashboardResponse } from '../../../core/api/player-dashboard.models';
import {
  dashboardFixture,
  insightFixture,
  insightsFixture,
} from '../../../core/player-dashboard/dashboard-fixtures';
import { AuthService } from '../../auth/auth.service';
import { FriendsService } from '../../friends/friends.service';
import { MatchHistoryComponent } from './match-history.component';

const recordsResponse: MemberMatchRecordsResponse = {
  matches: [
    {
      match_id: 'm1',
      round_number: 1,
      group_id: 'g1',
      group_name: '週三團',
      won: true,
      team_a: [{ roster_entry_id: 'p1', nickname: '小明', team: 'A', member_id: 'self-id' }],
      team_b: [{ roster_entry_id: 'p2', nickname: '小華', team: 'B', member_id: 'm2' }],
      score_a: 21,
      score_b: 15,
      winner_team: 'A',
      started_at: '2026-01-01T10:00:00Z',
      ended_at: '2026-01-01T10:15:00Z',
    },
  ],
  total_matches: 1,
  total_wins: 1,
  total_losses: 0,
  win_rate: 1,
  round_win_rates: [{ round_number: 1, wins: 1, losses: 0, win_rate: 1 }],
  opponent_records: [
    {
      player_key: 'm:m2',
      member_id: 'm2',
      nickname: '小華',
      wins: 1,
      losses: 0,
      matches: 1,
      win_rate: 1,
      avg_margin: 6,
      low_sample: true,
    },
  ],
  partner_records: [
    {
      player_key: 'r:p1',
      member_id: null,
      nickname: '阿哲',
      wins: 4,
      losses: 2,
      matches: 6,
      win_rate: 0.6667,
      avg_margin: 2.5,
      low_sample: false,
    },
  ],
  matchup_highlights: {
    most_played_partner: 'r:p1',
    best_partner: 'r:p1',
    most_faced_opponent: null,
    toughest_opponent: null,
  },
  doubles_matches: 6,
  page: 1,
  total_pages: 1,
};

const BENCHMARK_GROUPS: BenchmarkGroupOption[] = [
  { group_id: 'g-busy', group_number: 1, name: '週三羽球', status: 'active', member_status: 'active', my_completed_matches: 86 },
  { group_id: 'g-old', group_number: 2, name: '老球友', status: 'active', member_status: 'left', my_completed_matches: 12 },
];

function benchmarkResponse(groupId: string): GroupBenchmarkResponse {
  return {
    group: { group_id: groupId, name: groupId === 'g-busy' ? '週三羽球' : '老球友' },
    total_matches: 200,
    my_matches: 86,
    metrics: [],
    insights: insightsFixture({
      benchmark_group_name: '週三羽球',
      strengths: [
        insightFixture({
          rule: 'benchmark_quartile',
          source: 'benchmark',
          metric_key: 'team_serve',
          params: { mine: 0.6, group_average: 0.5, diff: 0.1, rank: 1, pool_size: 12, kind: 'rate' },
        }),
      ],
    }),
  };
}

const defaultCandidates: InviteCandidatesResponse = {
  candidates: [{ member_id: 'm2', friendship_status: 'none', invite_eligible: true }],
};

function setup(
  detailCalls: unknown[][] = [],
  options: {
    records?: MemberMatchRecordsResponse;
    candidates?: InviteCandidatesResponse;
    selfMemberId?: string | null;
    dashboard?: Observable<MemberMatchDashboardResponse>;
    dashboardCalls?: unknown[][];
    recordCalls?: unknown[][];
    benchmarkGroups?: Observable<BenchmarkGroupsResponse>;
    benchmark?: (groupId: string) => Observable<GroupBenchmarkResponse>;
    benchmarkCalls?: string[];
    benchmarkGroupCalls?: unknown[][];
    activities?: ActivitySummary[];
    sections?: Observable<DashboardSectionsResponse>;
    sectionsCalls?: unknown[][];
  } = {},
) {
  TestBed.configureTestingModule({
    imports: [MatchHistoryComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: AuthService,
        useValue: {
          getMatchRecords: (...args: unknown[]) => {
            options.recordCalls?.push(args);
            return of(options.records ?? recordsResponse);
          },
          getMatchDashboard: (...args: unknown[]) => {
            options.dashboardCalls?.push(args);
            return options.dashboard ?? of(dashboardFixture());
          },
          getBenchmarkGroups: (...args: unknown[]) => {
            options.benchmarkGroupCalls?.push(args);
            return options.benchmarkGroups ?? of({ groups: BENCHMARK_GROUPS });
          },
          getGroupBenchmark: (groupId: string) => {
            options.benchmarkCalls?.push(groupId);
            return (options.benchmark ?? ((id: string) => of(benchmarkResponse(id))))(groupId);
          },
          // 043: one activity (or none) keeps the page exactly as before.
          getActivities: () => of(options.activities ?? []),
          getDashboardSections: (...args: unknown[]) => {
            options.sectionsCalls?.push(args);
            return options.sections ?? of(SECTIONS_RESPONSE);
          },
          getMatchRecordDetail: (...args: unknown[]) => {
            detailCalls.push(args);
            return of(null);
          },
          getCachedMemberId: () => (options.selfMemberId === undefined ? 'self-id' : options.selfMemberId),
        },
      },
      {
        provide: FriendsService,
        useValue: {
          getInviteCandidatesStatus: () => of(options.candidates ?? defaultCandidates),
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(MatchHistoryComponent);
  fixture.detectChanges();
  return fixture;
}

describe('MatchHistoryComponent', () => {
  it('renders the cross-group match list', () => {
    const fixture = setup();

    expect(fixture.nativeElement.querySelectorAll('.match-card').length).toBe(1);
  });

  // 016-match-score-timeline (US1, T015a regression guard for I1): this
  // page (like group-history) MUST call AuthService's "ever a member"
  // endpoint, never GroupMemberViewService's active-membership one — a
  // cross-group list already includes matches from groups the member may
  // no longer be active in.
  it('clicking a row calls AuthService.getMatchRecordDetail with only the matchId', () => {
    const detailCalls: unknown[][] = [];
    const fixture = setup(detailCalls);

    const row = fixture.nativeElement.querySelector('.match-card') as HTMLElement;
    row.click();

    expect(detailCalls.length).toBe(1);
    expect(detailCalls[0]).toEqual(['m1']);
  });

  // 040-match-share-card FR-016: this list is the one "my matches" entry
  // point, so the share card takes the viewer's side — derived from the
  // row's own won/winner_team, never from who is logged in.
  describe('share card context', () => {
    function shareContextAfterClick(won: boolean) {
      const fixture = setup([], {
        records: {
          ...recordsResponse,
          matches: [{ ...recordsResponse.matches[0], won, winner_team: 'A' }],
        },
      });
      (fixture.nativeElement.querySelector('.match-card') as HTMLElement).click();
      fixture.detectChanges();
      const dialog = fixture.debugElement.query(By.directive(MatchRecordDetailDialogComponent))
        .componentInstance as MatchRecordDetailDialogComponent;
      return dialog.shareContext();
    }

    it('is my side (the winner) with the row’s group name when I won', () => {
      expect(shareContextAfterClick(true)).toEqual({
        groupName: '週三團',
        perspective: { kind: 'mine', myTeam: 'A' },
      });
    });

    it('is my side (the other team) when I lost', () => {
      expect(shareContextAfterClick(false)).toEqual({
        groupName: '週三團',
        perspective: { kind: 'mine', myTeam: 'B' },
      });
    });
  });

  // 025-delete-account follow-up
  it('shows a deleted participant\'s placeholder nickname muted in the match-card row', () => {
    const fixture = setup();
    // Patch after setup: cheaper than duplicating the whole response fixture.
    fixture.componentInstance.records.set({
      ...recordsResponse,
      matches: [
        {
          ...recordsResponse.matches[0],
          team_a: [{ roster_entry_id: 'p1', nickname: 'Deleted User', team: 'A' }],
        },
      ],
    });
    fixture.detectChanges();

    const deletedSpan = fixture.nativeElement.querySelector(
      '.match-card__team .nickname--deleted',
    ) as HTMLElement | null;
    expect(deletedSpan).not.toBeNull();
    expect(deletedSpan?.textContent).toContain('Deleted User');
  });

  // 026-match-record-friend-invite (US1, T016)
  it('renders the add-friend button next to a participant with a member_id, not self', () => {
    const fixture = setup();

    const buttons = fixture.nativeElement.querySelectorAll('app-add-friend-button');
    expect(buttons.length).toBe(1);
  });

  it('renders nothing for a Guest participant (no member_id)', () => {
    const fixture = setup(undefined, {
      records: {
        ...recordsResponse,
        matches: [
          {
            ...recordsResponse.matches[0],
            team_a: [{ roster_entry_id: 'p1', nickname: '小明' as const, team: 'A' as const }],
            team_b: [{ roster_entry_id: 'p3', nickname: '訪客', team: 'B' as const }],
          },
        ],
      },
      candidates: { candidates: [] },
    });

    expect(fixture.nativeElement.querySelectorAll('app-add-friend-button').length).toBe(0);
  });

  it('renders nothing for the viewer\'s own row even when it has a member_id', () => {
    const fixture = setup(undefined, {
      records: {
        ...recordsResponse,
        matches: [
          {
            ...recordsResponse.matches[0],
            team_a: [
              { roster_entry_id: 'p1', nickname: '小明', team: 'A' as const, member_id: 'self-id' },
            ],
            team_b: [],
          },
        ],
      },
      candidates: { candidates: [] },
    });

    expect(fixture.nativeElement.querySelectorAll('app-add-friend-button').length).toBe(0);
  });

  describe('date filter', () => {
    type SentFilters = Record<string, unknown>;
    const lastFilters = (calls: unknown[][], index: number): SentFilters =>
      calls[calls.length - 1][index] as SentFilters;

    it('sends the viewer\'s LOCAL days as instants, to the list and the dashboard alike', () => {
      const recordCalls: unknown[][] = [];
      const dashboardCalls: unknown[][] = [];
      const fixture = setup([], { recordCalls, dashboardCalls });

      fixture.componentInstance.filterForm.patchValue({
        date_from: '2026-09-21',
        date_to: '2026-09-30',
      });
      fixture.componentInstance.applyFilters();

      // "from" is that day's local midnight; an inclusive "to" is the NEXT
      // day's — the API's range is half-open.
      const expected = {
        ended_from: new Date(2026, 8, 21).toISOString(),
        ended_before: new Date(2026, 9, 1).toISOString(),
      };
      expect(lastFilters(recordCalls, 1)).toMatchObject(expected);
      expect(lastFilters(dashboardCalls, 0)).toMatchObject(expected);
      // the bare dates the server used to compare with UTC dates are gone
      expect(lastFilters(recordCalls, 1)).not.toHaveProperty('date_from');
      expect(lastFilters(recordCalls, 1)).not.toHaveProperty('date_to');
    });

    it('sends only the end that was filled in', () => {
      const recordCalls: unknown[][] = [];
      const fixture = setup([], { recordCalls });

      fixture.componentInstance.filterForm.patchValue({ date_to: '2026-12-31' });
      fixture.componentInstance.applyFilters();

      expect(lastFilters(recordCalls, 1)['ended_from']).toBeUndefined();
      expect(lastFilters(recordCalls, 1)['ended_before']).toBe(new Date(2027, 0, 1).toISOString());
      expect(fixture.componentInstance.hasActiveFilters()).toBe(true);
    });

    it('counts as no filter when both days are empty', () => {
      const recordCalls: unknown[][] = [];
      const fixture = setup([], { recordCalls });

      expect(lastFilters(recordCalls, 1)['ended_from']).toBeUndefined();
      expect(lastFilters(recordCalls, 1)['ended_before']).toBeUndefined();
      expect(fixture.componentInstance.hasActiveFilters()).toBe(false);
    });
  });

  // 034-clutch-points-player-dashboard (T023)
  describe('technique dashboard', () => {
    function applyFilter(fixture: ReturnType<typeof setup>, matchMode: string): void {
      fixture.componentInstance.filterForm.patchValue({ match_mode: matchMode });
      fixture.componentInstance.applyFilters();
      fixture.detectChanges();
    }

    it('is fetched once on load, with the same (empty) filters as the list', () => {
      const dashboardCalls: unknown[][] = [];
      const fixture = setup([], { dashboardCalls });

      expect(dashboardCalls).toEqual([[{}]]);
      expect(fixture.nativeElement.querySelectorAll('app-player-dashboard [data-metric]').length).toBe(23);
    });

    it('is fetched again when the filters change, never for a page flip', () => {
      const dashboardCalls: unknown[][] = [];
      const fixture = setup([], { dashboardCalls });

      fixture.componentInstance.goToPage(2);
      fixture.componentInstance.goToPage(1);
      expect(dashboardCalls.length).toBe(1);

      applyFilter(fixture, 'singles');
      expect(dashboardCalls.length).toBe(2);
      expect(dashboardCalls[1]).toEqual([{ match_mode: 'singles' }]);

      fixture.componentInstance.goToPage(2);
      expect(dashboardCalls.length).toBe(2);

      fixture.componentInstance.clearFilters();
      expect(dashboardCalls.length).toBe(3);
    });

    it('draws the landing court with singles lines only under the singles filter', () => {
      const fixture = setup();
      expect(fixture.componentInstance.singlesOnly()).toBe(false);

      applyFilter(fixture, 'singles');
      expect(fixture.componentInstance.singlesOnly()).toBe(true);

      applyFilter(fixture, 'doubles');
      expect(fixture.componentInstance.singlesOnly()).toBe(false);
    });

    it('failing leaves the record list untouched and says so inside the dashboard only', () => {
      const fixture = setup([], { dashboard: throwError(() => new Error('boom')) });
      const root: HTMLElement = fixture.nativeElement;

      expect(root.querySelectorAll('.match-card').length).toBe(1);
      expect(root.querySelector('app-player-dashboard [data-state="failed"]')).not.toBeNull();
      expect(root.querySelector('app-player-dashboard [data-metric]')).toBeNull();
      // 036: the summary rides on the same request — it stays out of the way.
      expect(root.querySelector('app-player-insights')).toBeNull();
    });
  });

  // 036-match-insights-benchmarks US3 (T042)
  describe('in-group comparison', () => {
    const SELF = 'self-id';
    const KEY = `rally-stats:benchmark-group:${SELF}`;
    const ownSummary = () =>
      of(
        dashboardFixture({
          insights: insightsFixture({
            strengths: [insightFixture({ metric_key: 'endgame' })],
          }),
        }),
      );
    const open = (fixture: ReturnType<typeof setup>) => {
      const details = (fixture.nativeElement as HTMLElement).querySelector<HTMLDetailsElement>(
        'app-group-benchmark details',
      )!;
      details.open = true;
      details.dispatchEvent(new Event('toggle'));
      fixture.detectChanges();
    };
    const summaryRules = (fixture: ReturnType<typeof setup>) =>
      Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll('app-player-insights .insight'),
      ).map((node) => node.getAttribute('data-rule'));

    afterEach(() => localStorage.clear());

    it('(a) asks for nothing until the block is opened, then uses my busiest group', () => {
      const benchmarkCalls: string[] = [];
      const benchmarkGroupCalls: unknown[][] = [];
      const fixture = setup([], { benchmarkCalls, benchmarkGroupCalls });
      expect(benchmarkGroupCalls.length).toBe(0);
      expect(benchmarkCalls.length).toBe(0);

      open(fixture);

      expect(benchmarkGroupCalls.length).toBe(1);
      expect(benchmarkCalls).toEqual(['g-busy']);
      expect(localStorage.getItem(KEY)).toBe('g-busy');
      open(fixture); // opening again is not another request
      expect(benchmarkGroupCalls.length).toBe(1);
    });

    it('(b) a group chosen on an earlier visit loads by itself, after the dashboard', () => {
      localStorage.setItem(KEY, 'g-old');
      const benchmarkCalls: string[] = [];
      setup([], { benchmarkCalls });
      expect(benchmarkCalls).toEqual(['g-old']);
    });

    it('(c) choosing another group remembers it and asks again', () => {
      const benchmarkCalls: string[] = [];
      const fixture = setup([], { benchmarkCalls });
      open(fixture);
      const select = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
        'app-group-benchmark select',
      )!;

      select.value = 'g-old';
      select.dispatchEvent(new Event('change'));
      fixture.detectChanges();

      expect(benchmarkCalls).toEqual(['g-busy', 'g-old']);
      expect(localStorage.getItem(KEY)).toBe('g-old');
    });

    it('(d) a remembered group that is no longer mine falls back to the default', () => {
      localStorage.setItem(KEY, 'g-gone');
      const benchmarkCalls: string[] = [];
      setup([], { benchmarkCalls });
      expect(benchmarkCalls).toEqual(['g-busy']);
      expect(localStorage.getItem(KEY)).toBe('g-busy');
    });

    it('(e) shows the merged summary while no filter is active, my own under a filter', () => {
      localStorage.setItem(KEY, 'g-busy');
      const fixture = setup([], { dashboard: ownSummary() });
      const root: HTMLElement = fixture.nativeElement;
      fixture.detectChanges();
      expect(summaryRules(fixture)).toEqual(['benchmark_quartile']);
      expect(root.querySelector('[data-benchmark-group]')).not.toBeNull();

      fixture.componentInstance.filterForm.patchValue({ result: 'win' });
      fixture.componentInstance.applyFilters();
      fixture.detectChanges();

      expect(summaryRules(fixture)).toEqual(['rate_vs_overall']);
      expect(root.querySelector('[data-benchmark-omitted]')).not.toBeNull();

      fixture.componentInstance.clearFilters();
      fixture.detectChanges();
      expect(summaryRules(fixture)).toEqual(['benchmark_quartile']);
      expect(root.querySelector('[data-benchmark-omitted]')).toBeNull();
    });

    it('(e) says so while the benchmark is on its way', () => {
      localStorage.setItem(KEY, 'g-busy');
      const pending = new Subject<GroupBenchmarkResponse>();
      const fixture = setup([], { dashboard: ownSummary(), benchmark: () => pending });
      fixture.detectChanges();
      const root: HTMLElement = fixture.nativeElement;
      expect(root.querySelector('[data-benchmark-pending]')).not.toBeNull();
      expect(summaryRules(fixture)).toEqual(['rate_vs_overall']); // mine, meanwhile

      pending.next(benchmarkResponse('g-busy'));
      fixture.detectChanges();
      expect(root.querySelector('[data-benchmark-pending]')).toBeNull();
      expect(summaryRules(fixture)).toEqual(['benchmark_quartile']);
    });

    it('(f) a failure stays inside its own block', () => {
      localStorage.setItem(KEY, 'g-busy');
      const fixture = setup([], {
        dashboard: ownSummary(),
        benchmark: () => throwError(() => new Error('boom')),
      });
      fixture.detectChanges();
      const root: HTMLElement = fixture.nativeElement;

      expect(root.querySelector('app-group-benchmark [data-failed]')).not.toBeNull();
      expect(summaryRules(fixture)).toEqual(['rate_vs_overall']);
      expect(root.querySelectorAll('.match-card').length).toBe(1);
      expect(root.querySelectorAll('app-player-dashboard [data-metric]').length).toBe(23);
    });

    it('is never bound to the page filters', () => {
      localStorage.setItem(KEY, 'g-busy');
      const benchmarkCalls: string[] = [];
      const fixture = setup([], { benchmarkCalls });
      fixture.componentInstance.filterForm.patchValue({ result: 'win' });
      fixture.componentInstance.applyFilters();
      expect(benchmarkCalls).toEqual(['g-busy']); // asked once, not again per filter
    });
  });

  // 036-match-insights-benchmarks US2 (T027)
  describe('partners and opponents', () => {
    it('replaces the opponent ranking with a partner table and an opponent table', () => {
      const root: HTMLElement = setup([]).nativeElement;

      expect(root.querySelector('.opponent-ranking')).toBeNull();
      const tables = root.querySelectorAll('app-matchup-records');
      expect(tables.length).toBe(2);
      expect(tables[0].querySelector('[data-role="partner"] [data-player="r:p1"]')).not.toBeNull();
      expect(tables[1].querySelector('[data-role="opponent"] [data-player="m:m2"]')).not.toBeNull();
      // Partner highlights map to the partner table, never to the opponent one.
      expect(tables[0].querySelector('[data-highlights]')).not.toBeNull();
      expect(tables[1].querySelector('[data-highlights]')).toBeNull();
    });

    it('says singles has no partner instead of showing an empty table', () => {
      const fixture = setup([]);
      fixture.componentInstance.records.set({
        ...fixture.componentInstance.records()!,
        partner_records: [],
        doubles_matches: 0,
      });
      fixture.detectChanges();

      const partners = (fixture.nativeElement as HTMLElement).querySelector('[data-role="partner"]')!;
      expect(partners.querySelector('[data-empty]')?.textContent).toContain(
        'member.matchHistory.matchups.noDoubles',
      );
    });

    it('a click on a partner narrows BOTH requests to that exact player, from page 1', () => {
      const dashboardCalls: unknown[][] = [];
      const recordCalls: unknown[][] = [];
      const fixture = setup([], { dashboardCalls, recordCalls });
      fixture.componentInstance.goToPage(3);
      const root: HTMLElement = fixture.nativeElement;

      root.querySelector<HTMLButtonElement>('[data-role="partner"] [data-player="r:p1"] button')!.click();
      fixture.detectChanges();

      expect(recordCalls.at(-1)).toEqual([1, { partner_key: 'r:p1' }]);
      expect(dashboardCalls.at(-1)).toEqual([{ partner_key: 'r:p1' }]);
      expect(fixture.componentInstance.hasActiveFilters()).toBe(true);
      const chip = root.querySelector('[data-picked-player]')!;
      expect(chip.textContent).toContain('member.matchHistory.matchups.activePartner');
    });

    it('an opponent click sends opponent_key, and replaces an earlier partner pick', () => {
      const recordCalls: unknown[][] = [];
      const fixture = setup([], { recordCalls });
      const root: HTMLElement = fixture.nativeElement;
      root.querySelector<HTMLButtonElement>('[data-role="partner"] [data-player="r:p1"] button')!.click();
      fixture.detectChanges();

      root.querySelector<HTMLButtonElement>('[data-role="opponent"] [data-player="m:m2"] button')!.click();
      fixture.detectChanges();

      expect(recordCalls.at(-1)).toEqual([1, { opponent_key: 'm:m2' }]);
      expect(root.querySelector('[data-picked-player]')!.textContent).toContain(
        'member.matchHistory.matchups.activeOpponent',
      );
    });

    it('the chip clears only the picked player; the form filters stay', () => {
      const recordCalls: unknown[][] = [];
      const fixture = setup([], { recordCalls });
      const root: HTMLElement = fixture.nativeElement;
      fixture.componentInstance.filterForm.patchValue({ result: 'win' });
      root.querySelector<HTMLButtonElement>('[data-role="partner"] [data-player="r:p1"] button')!.click();
      fixture.detectChanges();
      expect(recordCalls.at(-1)).toEqual([1, { result: 'win', partner_key: 'r:p1' }]);

      root.querySelector<HTMLButtonElement>('[data-picked-player] button')!.click();
      fixture.detectChanges();

      expect(recordCalls.at(-1)).toEqual([1, { result: 'win' }]);
      expect(root.querySelector('[data-picked-player]')).toBeNull();
    });

    it('"clear filters" clears the picked player along with the form', () => {
      const recordCalls: unknown[][] = [];
      const fixture = setup([], { recordCalls });
      fixture.componentInstance.filterForm.patchValue({ result: 'win' });
      (fixture.nativeElement as HTMLElement)
        .querySelector<HTMLButtonElement>('[data-role="partner"] [data-player="r:p1"] button')!
        .click();
      fixture.detectChanges();

      fixture.componentInstance.clearFilters();
      fixture.detectChanges();

      expect(recordCalls.at(-1)).toEqual([1, {}]);
      expect(fixture.componentInstance.pickedPlayer()).toBeNull();
      expect(fixture.componentInstance.hasActiveFilters()).toBe(false);
    });

    it('has no active filter on a plain first load (undefined values are not filters)', () => {
      expect(setup([]).componentInstance.hasActiveFilters()).toBe(false);
    });

    it('a matchup sentence in the summary leads to that player\'s row', () => {
      const fixture = setup([], {
        dashboard: of(
          dashboardFixture({
            insights: insightsFixture({
              matchups: [
                insightFixture({
                  list: 'matchup',
                  rule: 'partner_above_overall',
                  metric_key: null,
                  player: { key: 'r:p1', nickname: '阿哲', member_id: null },
                  params: { win_rate: 0.67, matches: 6, wins: 4, losses: 2, baseline: 0.4, diff: 0.27 },
                }),
              ],
            }),
          }),
        ),
      });
      const root: HTMLElement = fixture.nativeElement;
      document.body.appendChild(root);
      const details = root.querySelector<HTMLDetailsElement>('[data-role="partner"]')!;
      details.open = false;

      root.querySelector<HTMLButtonElement>('app-player-insights [data-list="matchup"] .insight')!.click();

      expect(details.open).toBe(true);
      expect(document.activeElement).toBe(root.querySelector('#matchup-partner-r\\:p1 button'));
      root.remove();
    });
  });

  // 036-match-insights-benchmarks US1 (T014)
  describe('strengths and weaknesses summary', () => {
    it('sits above the dashboard and shows what the dashboard response carries', () => {
      const fixture = setup([], {
        dashboard: of(
          dashboardFixture({
            insights: insightsFixture({
              weaknesses: [insightFixture({ list: 'weakness', metric_key: 'team_receive' })],
            }),
          }),
        ),
      });
      const root: HTMLElement = fixture.nativeElement;

      const summary = root.querySelector('app-player-insights')!;
      const dashboard = root.querySelector('app-player-dashboard')!;
      expect(summary.compareDocumentPosition(dashboard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(summary.querySelector('[data-list="weakness"] [data-sentence]')?.textContent).toContain(
        'playerInsights.rule.rate_vs_overall.weakness',
      );
    });

    it('jumps to the metric card an insight is about', () => {
      const fixture = setup([], {
        dashboard: of(
          dashboardFixture({
            insights: insightsFixture({
              strengths: [insightFixture({ metric_key: 'winner_share' })],
            }),
          }),
        ),
      });
      const root: HTMLElement = fixture.nativeElement;
      document.body.appendChild(root);
      const group = root.querySelector<HTMLDetailsElement>('[data-group="ending"]')!;
      expect(group.open).toBe(false);

      root.querySelector<HTMLButtonElement>('app-player-insights .insight')!.click();

      expect(group.open).toBe(true);
      expect(document.activeElement).toBe(root.querySelector('#metric-winner_share'));
      root.remove();
    });
  });

  // On a phone the list sits thousands of pixels below the summary and the
  // dashboard: a jump button gets there, and a page flip lands on the NEW
  // page's first card rather than at the pagination under it.
  // Two tabs under the summary: the matches (first) and the analysis.
  describe('matches and analysis tabs', () => {
    const tab = (root: HTMLElement, name: string) =>
      root.querySelector<HTMLButtonElement>(`[role="tab"][data-tab="${name}"]`)!;
    const panel = (root: HTMLElement, name: string) =>
      root.querySelector<HTMLElement>(`[role="tabpanel"][data-panel="${name}"]`)!;

    it('opens on the matches, with the total in the tab', () => {
      const fixture = setup([], { records: { ...recordsResponse, total_matches: 42 } });
      const root: HTMLElement = fixture.nativeElement;

      expect(tab(root, 'matches').getAttribute('aria-selected')).toBe('true');
      expect(tab(root, 'stats').getAttribute('aria-selected')).toBe('false');
      expect(tab(root, 'matches').textContent).toContain('member.matchHistory.tabs.matches');
      expect(panel(root, 'matches').hidden).toBe(false);
      expect(panel(root, 'stats').hidden).toBe(true);
      expect(panel(root, 'matches').querySelector('.match-card')).not.toBeNull();
      expect(panel(root, 'stats').querySelector('app-player-dashboard')).not.toBeNull();
    });

    it('switches to the analysis and back, keeping both rendered', () => {
      const fixture = setup();
      const root: HTMLElement = fixture.nativeElement;

      tab(root, 'stats').click();
      fixture.detectChanges();
      expect(tab(root, 'stats').getAttribute('aria-selected')).toBe('true');
      expect(panel(root, 'stats').hidden).toBe(false);
      expect(panel(root, 'matches').hidden).toBe(true);

      tab(root, 'matches').click();
      fixture.detectChanges();
      expect(panel(root, 'matches').hidden).toBe(false);
      expect(panel(root, 'stats').hidden).toBe(true);
    });

    it('picking a partner shows their matches on the matches tab', () => {
      const fixture = setup();
      const root: HTMLElement = fixture.nativeElement;
      tab(root, 'stats').click();
      fixture.detectChanges();

      fixture.componentInstance.pickPlayer('partner', recordsResponse.partner_records[0]);
      fixture.detectChanges();

      expect(panel(root, 'matches').hidden).toBe(false);
      expect(root.querySelector('[data-picked-player]')).not.toBeNull();
    });

    it('has no jump-to-list button any more — the tab is the way there', () => {
      const fixture = setup();
      expect(fixture.nativeElement.querySelector('[data-jump-to-list]')).toBeNull();
    });
  });

  describe('paging the match list', () => {
    function spyOnListScroll(fixture: ReturnType<typeof setup>) {
      const list = fixture.nativeElement.querySelector('#match-list') as HTMLElement;
      const scroll = vi.fn();
      list.scrollIntoView = scroll;
      return scroll;
    }

    it('a page flip brings the top of the new page into view', () => {
      const fixture = setup();
      const scroll = spyOnListScroll(fixture);

      fixture.componentInstance.goToPage(2);

      expect(scroll).toHaveBeenCalledTimes(1);
    });

    it('applying filters does not scroll — the reader is looking at the form', () => {
      const fixture = setup();
      const scroll = spyOnListScroll(fixture);

      fixture.componentInstance.applyFilters();

      expect(scroll).not.toHaveBeenCalled();
    });
  });

  // The big sections run as an accordion: all folded on arrival, and
  // opening one folds whichever was open.
  describe('sections as an accordion', () => {
    const SECTIONS = ['insights', 'dashboard', 'benchmark', 'roundTrend', 'partners', 'opponents'];

    // Opening the group comparison remembers a group, which would then load
    // by itself in the next test and take over the summary.
    afterEach(() => localStorage.clear());

    /** The <details> of a section — the panel itself, or the one a child
     * component renders inside its host. */
    function panel(root: HTMLElement, section: string): HTMLDetailsElement {
      const el = root.querySelector<HTMLElement>(`[data-section="${section}"]`)!;
      return (el instanceof HTMLDetailsElement ? el : el.querySelector('details'))!;
    }

    /** What a tap on the summary does: flip `open`, then `toggle` fires. */
    function tap(fixture: ReturnType<typeof setup>, section: string): void {
      const details = panel(fixture.nativeElement, section);
      details.open = !details.open;
      details.dispatchEvent(new Event('toggle'));
      fixture.detectChanges();
    }

    const openSections = (root: HTMLElement) => SECTIONS.filter((section) => panel(root, section).open);

    it('shows every section, all folded, on arrival', () => {
      const fixture = setup();
      const root: HTMLElement = fixture.nativeElement;

      for (const section of SECTIONS) {
        expect(panel(root, section), section).toBeTruthy();
      }
      expect(openSections(root)).toEqual([]);
    });

    it('opening one section folds the one that was open', () => {
      const fixture = setup();
      const root: HTMLElement = fixture.nativeElement;

      tap(fixture, 'insights');
      expect(openSections(root)).toEqual(['insights']);

      tap(fixture, 'dashboard');
      expect(openSections(root)).toEqual(['dashboard']);

      tap(fixture, 'partners');
      expect(openSections(root)).toEqual(['partners']);
      expect(fixture.componentInstance.sections.openSection()).toBe('partners');
    });

    it('folding the open section leaves every section folded', () => {
      const fixture = setup();
      const root: HTMLElement = fixture.nativeElement;

      tap(fixture, 'roundTrend');
      tap(fixture, 'roundTrend');

      expect(openSections(root)).toEqual([]);
      expect(fixture.componentInstance.sections.openSection()).toBeNull();
    });

    it('opening the group comparison still starts loading it', () => {
      const benchmarkGroupCalls: unknown[][] = [];
      const fixture = setup([], { benchmarkGroupCalls });

      tap(fixture, 'benchmark');

      expect(benchmarkGroupCalls.length).toBe(1);
      expect(openSections(fixture.nativeElement)).toEqual(['benchmark']);
    });

    it('an insight about a metric opens the dashboard and folds the summary', () => {
      const fixture = setup([], {
        dashboard: of(
          dashboardFixture({
            insights: insightsFixture({ strengths: [insightFixture({ metric_key: 'winner_share' })] }),
          }),
        ),
      });
      const root: HTMLElement = fixture.nativeElement;
      document.body.appendChild(root);
      tap(fixture, 'insights');

      root.querySelector<HTMLButtonElement>('app-player-insights .insight')!.click();

      expect(openSections(root)).toEqual(['dashboard']);
      expect(document.activeElement).toBe(root.querySelector('#metric-winner_share'));
      root.remove();
    });

    it('an opened section whose title the fold pushed off screen is scrolled back to', () => {
      const fixture = setup();
      const root: HTMLElement = fixture.nativeElement;
      const dashboard = root.querySelector<HTMLElement>('[data-section="dashboard"]')!;
      const scroll = vi.fn();
      dashboard.scrollIntoView = scroll;
      vi.spyOn(dashboard, 'getBoundingClientRect').mockReturnValue({ top: -300 } as DOMRect);

      tap(fixture, 'dashboard');

      expect(scroll).toHaveBeenCalledWith({ block: 'start' });
    });

    it('does not scroll when the opened section is already in view', () => {
      const fixture = setup();
      const root: HTMLElement = fixture.nativeElement;
      const dashboard = root.querySelector<HTMLElement>('[data-section="dashboard"]')!;
      const scroll = vi.fn();
      dashboard.scrollIntoView = scroll;
      vi.spyOn(dashboard, 'getBoundingClientRect').mockReturnValue({ top: 200 } as DOMRect);

      tap(fixture, 'dashboard');

      expect(scroll).not.toHaveBeenCalled();
    });
  });
});

// --- 043 FR-026: activity tabs -------------------------------------------

const NOUNS = { venue: 'court', score: 'point', member: 'player' } as const;
const ACTIVITIES: ActivitySummary[] = [
  {
    sport: { sport_key: 'billiards', type_key: 'frames', name_key: 'sports.billiards.name', name: null, icon: 'billiards', nouns: NOUNS },
    filter_value: 'billiards',
    match_count: 5,
  },
  {
    sport: { sport_key: 'badminton', type_key: 'net_rally', name_key: 'sports.badminton.name', name: null, icon: 'badminton', nouns: NOUNS },
    filter_value: 'badminton',
    match_count: 2,
  },
];
const SECTIONS_RESPONSE: DashboardSectionsResponse = {
  sport: ACTIVITIES[0].sport,
  type_key: 'frames',
  total_matches: 5,
  sections: [{ kind: 'text_note', title_key: null, data: { text_key: 'playerDashboard.empty' } }],
};

describe('MatchHistoryComponent activity tabs (043)', () => {
  it('one activity: no tab row, no sport filter', () => {
    const recordCalls: unknown[][] = [];
    const fixture = setup([], { recordCalls, activities: [ACTIVITIES[1]] });
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.activity-tabs')).toBeNull();
    expect(recordCalls.every((call) => (call[1] as { sport?: string }).sport === undefined)).toBe(true);
  });

  it('several activities: the most played is chosen and filters the page', () => {
    const recordCalls: unknown[][] = [];
    const sectionsCalls: unknown[][] = [];
    const dashboardCalls: unknown[][] = [];
    const fixture = setup([], { recordCalls, sectionsCalls, dashboardCalls, activities: ACTIVITIES });
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const tabs = [...el.querySelectorAll('.activity-tabs [data-activity]')];
    expect(tabs.map((tab) => tab.getAttribute('data-activity'))).toEqual(['billiards', 'badminton']);
    expect(tabs[0].getAttribute('aria-selected')).toBe('true');
    expect((recordCalls.at(-1)?.[1] as { sport?: string }).sport).toBe('billiards');
    // Frames: the sections dashboard, not the net rally one.
    expect((sectionsCalls.at(-1)?.[0] as { sport?: string }).sport).toBe('billiards');
    expect(el.querySelector('[data-section="activity-dashboard"]')).not.toBeNull();
    expect(el.querySelector('app-player-dashboard')).toBeNull();

    (tabs[1] as HTMLButtonElement).click();
    fixture.detectChanges();
    expect((recordCalls.at(-1)?.[1] as { sport?: string }).sport).toBe('badminton');
    expect((dashboardCalls.at(-1)?.[0] as { sport?: string }).sport).toBe('badminton');
    expect(el.querySelector('app-player-dashboard')).not.toBeNull();
  });
});
