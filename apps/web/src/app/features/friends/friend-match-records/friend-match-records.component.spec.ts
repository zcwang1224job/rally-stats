import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { ApiError } from '../../../core/api/api-error';
import {
  MatchRecordDetailResponse,
  MemberMatchRecordsResponse,
} from '../../../core/api/group-member-view.models';
import {
  dashboardFixture,
  insightFixture,
  insightsFixture,
} from '../../../core/player-dashboard/dashboard-fixtures';
import { MatchComparisonResponse } from '../../../core/api/match-comparison.models';
import { AuthService } from '../../auth/auth.service';
import { FriendMatchRecordsComponent } from './friend-match-records.component';

const oneMatch: MemberMatchRecordsResponse = {
  matches: [
    {
      match_id: 'match-1',
      round_number: 2,
      team_a: [{ roster_entry_id: 'r1', nickname: '小美', team: 'A' }],
      team_b: [{ roster_entry_id: 'r2', nickname: '小華', team: 'B' }],
      score_a: 21,
      score_b: 15,
      winner_team: 'A',
      started_at: '2026-09-14T10:00:00Z',
      ended_at: '2026-09-14T10:20:00Z',
      group_id: 'g1',
      group_name: '週末羽球團',
      won: true,
    },
  ],
  total_matches: 1,
  total_wins: 1,
  total_losses: 0,
  win_rate: 1,
  round_win_rates: [],
  opponent_records: [],
  partner_records: [],
  matchup_highlights: {
    most_played_partner: null,
    best_partner: null,
    most_faced_opponent: null,
    toughest_opponent: null,
  },
  doubles_matches: 0,
  page: 1,
  total_pages: 1,
};

const emptyRecords: MemberMatchRecordsResponse = {
  matches: [],
  total_matches: 0,
  total_wins: 0,
  total_losses: 0,
  win_rate: 0,
  round_win_rates: [],
  opponent_records: [],
  partner_records: [],
  matchup_highlights: {
    most_played_partner: null,
    best_partner: null,
    most_faced_opponent: null,
    toughest_opponent: null,
  },
  doubles_matches: 0,
  page: 1,
  total_pages: 1,
};

const COMPARISON: MatchComparisonResponse = {
  friend_total_matches: 12,
  my_total_matches: 9,
  metrics: [
    {
      key: 'team_serve',
      kind: 'rate',
      better_when: 'higher',
      friend: { value: 0.5, numerator: 50, denominator: 100, matches_used: 8 },
      me: { value: 0.6, numerator: 60, denominator: 100, matches_used: 6 },
      better: 'me',
    },
  ],
  head_to_head: { as_opponents: null, as_partners: null },
};

function setup(options: {
  nickname?: string | null;
  getFriendMatchRecords?: () => unknown;
  getFriendMatchRecordDetail?: () => unknown;
  getFriendMatchDashboard?: () => unknown;
  getFriendMatchComparison?: () => unknown;
}) {
  const getFriendMatchRecordsCalls: unknown[][] = [];
  const getFriendMatchDashboardCalls: unknown[][] = [];
  const getFriendMatchComparisonCalls: unknown[][] = [];
  const authServiceStub = {
    getFriendMatchRecords: (...args: unknown[]) => {
      getFriendMatchRecordsCalls.push(args);
      return (options.getFriendMatchRecords ?? (() => of(oneMatch)))();
    },
    getFriendMatchDashboard: (...args: unknown[]) => {
      getFriendMatchDashboardCalls.push(args);
      return (options.getFriendMatchDashboard ?? (() => of(dashboardFixture())))();
    },
    getFriendMatchComparison: (...args: unknown[]) => {
      getFriendMatchComparisonCalls.push(args);
      return (options.getFriendMatchComparison ?? (() => of(COMPARISON)))();
    },
    getFriendMatchRecordDetail:
      options.getFriendMatchRecordDetail ??
      (() =>
        of({
          match_id: 'match-1',
          round_number: 2,
          team_a: [{ roster_entry_id: 'r1', nickname: '小美', team: 'A' }],
          team_b: [{ roster_entry_id: 'r2', nickname: '小華', team: 'B' }],
          score_a: 21,
          score_b: 15,
          winner_team: 'A',
          started_at: '2026-09-14T10:00:00Z',
          ended_at: '2026-09-14T10:20:00Z',
          target_score: 21,
          record_completeness: 'complete',
          events: [],
          player_stats: [],
          serve_stats: null,
          momentum_stats: null,
          tempo_stats: null,
          landing_distribution: [],
          clutch_stats: null,
          ending_stats: null,
        } satisfies MatchRecordDetailResponse)),
  };

  TestBed.configureTestingModule({
    imports: [FriendMatchRecordsComponent],
    providers: [
      provideTranslateService({}),
      { provide: AuthService, useValue: authServiceStub },
      {
        provide: ActivatedRoute,
        useValue: {
          snapshot: {
            paramMap: convertToParamMap({ memberId: 'friend-1' }),
            queryParamMap: convertToParamMap(
              'nickname' in options && options.nickname !== undefined
                ? options.nickname === null
                  ? {}
                  : { nickname: options.nickname }
                : { nickname: '小美' },
            ),
          },
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(FriendMatchRecordsComponent);
  fixture.detectChanges();
  return {
    fixture,
    getFriendMatchRecordsCalls,
    getFriendMatchDashboardCalls,
    getFriendMatchComparisonCalls,
  };
}

describe('FriendMatchRecordsComponent', () => {
  // US1
  it('loads the friend match records on init and renders the list newest-first with aggregate stats', () => {
    const { fixture, getFriendMatchRecordsCalls } = setup({});

    expect(getFriendMatchRecordsCalls).toEqual([['friend-1', 1]]);
    const rows = fixture.nativeElement.querySelectorAll('.match-card');
    expect(rows.length).toBe(1);
    expect(fixture.nativeElement.textContent).toContain('小美');
    expect(fixture.nativeElement.textContent).toContain('小華');
  });

  it('uses the nickname-specific title key when a nickname query param is present', () => {
    const { fixture } = setup({ nickname: '小美' });

    const title = fixture.nativeElement.querySelector('h1')?.textContent ?? '';
    expect(title).toContain('friendMatchRecords.title');
    expect(title).not.toContain('friendMatchRecords.titleGeneric');
  });

  it('falls back to the generic title key when no nickname query param is present (direct URL access)', () => {
    const { fixture } = setup({ nickname: null });

    const title = fixture.nativeElement.querySelector('h1')?.textContent ?? '';
    expect(title).toContain('friendMatchRecords.titleGeneric');
  });

  it('paginating calls getFriendMatchRecords with the new page number', () => {
    const { fixture, getFriendMatchRecordsCalls } = setup({
      getFriendMatchRecords: () =>
        of({ ...oneMatch, total_pages: 3 } satisfies MemberMatchRecordsResponse),
    });

    const nextPageButton = Array.from<HTMLButtonElement>(
      fixture.nativeElement.querySelectorAll('.pagination button'),
    ).find((btn) => btn.textContent?.trim() === '2');
    nextPageButton?.click();
    fixture.detectChanges();

    expect(getFriendMatchRecordsCalls).toEqual([
      ['friend-1', 1],
      ['friend-1', 2],
    ]);
  });

  // US1: three rejection error codes + empty state, each distinguishable
  it.each([
    ['MEMBER_NOT_FOUND', 'errors.MEMBER_NOT_FOUND'],
    ['FRIENDSHIP_REQUIRED', 'errors.FRIENDSHIP_REQUIRED'],
    ['MATCH_RECORDS_PRIVATE', 'errors.MATCH_RECORDS_PRIVATE'],
  ])('shows the %s rejection message, not a blank page', (errorCode, i18nKey) => {
    const { fixture } = setup({
      getFriendMatchRecords: () =>
        throwError(
          () =>
            ({
              errorCode,
              i18nKey,
              detail: null,
              status: 403,
            }) satisfies ApiError,
        ),
    });

    const alert = fixture.nativeElement.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert.textContent).toContain(i18nKey);
    expect(fixture.nativeElement.querySelector('.match-card')).toBeNull();
  });

  it('shows a distinct empty state (not the [role="alert"] error styling) when the friend has no match records', () => {
    const { fixture } = setup({ getFriendMatchRecords: () => of(emptyRecords) });

    expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
    const empty = fixture.nativeElement.querySelector('.empty-state');
    expect(empty).not.toBeNull();
    expect(empty.textContent?.length).toBeGreaterThan(0);
  });

  it('does not cache the authorization outcome: reloading (paginating) re-calls the endpoint every time', () => {
    let callCount = 0;
    const { fixture } = setup({
      getFriendMatchRecords: () => {
        callCount += 1;
        return of({ ...oneMatch, total_pages: 2, page: callCount });
      },
    });
    expect(callCount).toBe(1);

    const page2Button = Array.from<HTMLButtonElement>(
      fixture.nativeElement.querySelectorAll('.pagination button'),
    ).find((btn) => btn.textContent?.trim() === '2');
    page2Button?.click();
    fixture.detectChanges();

    expect(callCount).toBe(2);
  });

  // US2
  it('clicking a match row opens the detail dialog with data from getFriendMatchRecordDetail', () => {
    const { fixture } = setup({});

    const row = fixture.nativeElement.querySelector('.match-card') as HTMLElement;
    row.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('小美');
    expect(fixture.componentInstance.detail()?.match_id).toBe('match-1');
  });

  // Polish: FR-011 — no notification side effects. The component is only
  // ever given `AuthService` (which has no notify-style method) and
  // `ActivatedRoute` as dependencies — TestBed's strict DI would fail this
  // very setup() if the component tried to inject a NotificationService or
  // similar that this test doesn't provide, so viewing the list and
  // opening a match detail completing without error IS the evidence that
  // no notification side channel was wired in.
  it('viewing the list and opening a match detail completes with no unexpected dependency on a notification service', () => {
    const { fixture } = setup({});

    const row = fixture.nativeElement.querySelector('.match-card') as HTMLElement;
    expect(() => {
      row.click();
      fixture.detectChanges();
    }).not.toThrow();
    expect(fixture.componentInstance.detail()?.match_id).toBe('match-1');
  });

  // 034-clutch-points-player-dashboard US5 (T037)
  describe('technique dashboard', () => {
    const refused = (errorCode: string) => () =>
      throwError(
        () =>
          ({ errorCode, i18nKey: `errors.${errorCode}`, detail: null, status: 403 }) satisfies ApiError,
      );

    it('loads the friend\'s dashboard once, unfiltered, and not again on a page flip', () => {
      const { fixture, getFriendMatchDashboardCalls } = setup({
        getFriendMatchRecords: () => of({ ...oneMatch, total_pages: 3 } satisfies MemberMatchRecordsResponse),
      });

      expect(getFriendMatchDashboardCalls).toEqual([['friend-1']]);
      expect(fixture.nativeElement.querySelectorAll('app-player-dashboard [data-metric]').length).toBe(23);

      fixture.componentInstance.goToPage(2);
      expect(getFriendMatchDashboardCalls.length).toBe(1);
    });

    it('shows exactly one message when sharing is off — the page\'s own (US5 scenario 2)', () => {
      const { fixture } = setup({
        getFriendMatchRecords: refused('MATCH_RECORDS_PRIVATE'),
        getFriendMatchDashboard: refused('MATCH_RECORDS_PRIVATE'),
      });
      const root: HTMLElement = fixture.nativeElement;

      expect(root.querySelectorAll('[role="alert"]').length).toBe(1);
      expect(root.querySelector('app-player-dashboard')).toBeNull();
    });

    it('stays silent when only the dashboard fails; the records still show', () => {
      const { fixture } = setup({ getFriendMatchDashboard: refused('FRIENDSHIP_REQUIRED') });
      const root: HTMLElement = fixture.nativeElement;

      expect(root.querySelectorAll('.match-card').length).toBe(1);
      expect(root.querySelector('app-player-dashboard')).toBeNull();
      expect(root.querySelector('[role="alert"]')).toBeNull();
    });

    it('drops an already-shown dashboard once the records are refused (023 FR-007)', () => {
      let allowed = true;
      const { fixture } = setup({
        getFriendMatchRecords: () =>
          allowed
            ? of({ ...oneMatch, total_pages: 2 } satisfies MemberMatchRecordsResponse)
            : refused('MATCH_RECORDS_PRIVATE')(),
      });
      expect(fixture.nativeElement.querySelector('app-player-dashboard')).not.toBeNull();

      allowed = false; // the friend turns sharing off while the page is open
      fixture.componentInstance.goToPage(2);
      fixture.detectChanges();

      expect(fixture.componentInstance.dashboard()).toBeNull();
      expect(fixture.nativeElement.querySelector('app-player-dashboard')).toBeNull();
      // 036: the summary lives and dies with the dashboard it rides on.
      expect(fixture.nativeElement.querySelector('app-player-insights')).toBeNull();
    });
  });

  // 036-match-insights-benchmarks US4 (T050)
  describe('compare with me', () => {
    const toggle = (root: HTMLElement) =>
      root.querySelector<HTMLButtonElement>('[data-compare-toggle]')!;

    it('asks for nothing until the button is pressed, and then only once', () => {
      const { fixture, getFriendMatchComparisonCalls } = setup({});
      const root: HTMLElement = fixture.nativeElement;
      expect(getFriendMatchComparisonCalls.length).toBe(0);
      expect(root.querySelector('app-friend-comparison')).toBeNull();
      expect(toggle(root).getAttribute('aria-pressed')).toBe('false');

      toggle(root).click();
      fixture.detectChanges();
      expect(getFriendMatchComparisonCalls).toEqual([['friend-1']]);
      expect(toggle(root).getAttribute('aria-pressed')).toBe('true');
      expect(root.querySelector('app-friend-comparison [data-metric="team_serve"]')).not.toBeNull();

      toggle(root).click(); // hide…
      toggle(root).click(); // …and show again: no second request
      fixture.detectChanges();
      expect(getFriendMatchComparisonCalls.length).toBe(1);
      expect(root.querySelector('app-friend-comparison [data-better-mark]')).not.toBeNull();
    });

    it('a failure says so inside the comparison and leaves the rest alone', () => {
      const { fixture } = setup({
        getFriendMatchComparison: () => throwError(() => new Error('boom')),
      });
      const root: HTMLElement = fixture.nativeElement;
      toggle(root).click();
      fixture.detectChanges();

      expect(root.querySelector('app-friend-comparison [data-failed]')).not.toBeNull();
      expect(root.querySelectorAll('.match-card').length).toBe(1);
      expect(root.querySelector('app-player-dashboard')).not.toBeNull();
    });

    it('drops a comparison already on screen once the records are refused (023 FR-007)', () => {
      let allowed = true;
      const { fixture } = setup({
        getFriendMatchRecords: () =>
          allowed
            ? of({ ...oneMatch, total_pages: 2 } satisfies MemberMatchRecordsResponse)
            : throwError(
                () =>
                  ({
                    errorCode: 'MATCH_RECORDS_PRIVATE',
                    i18nKey: 'errors.MATCH_RECORDS_PRIVATE',
                    detail: null,
                    status: 403,
                  }) satisfies ApiError,
              ),
      });
      const root: HTMLElement = fixture.nativeElement;
      toggle(root).click();
      fixture.detectChanges();
      expect(root.querySelector('app-friend-comparison')).not.toBeNull();

      allowed = false;
      fixture.componentInstance.goToPage(2);
      fixture.detectChanges();

      expect(root.querySelector('app-friend-comparison')).toBeNull();
      expect(fixture.componentInstance.comparison()).toBeNull();
    });

    it('never shows an in-group comparison on a friend\'s page (FR-037)', () => {
      const { fixture } = setup({});
      expect(fixture.nativeElement.querySelector('app-group-benchmark')).toBeNull();
    });
  });

  // 036-match-insights-benchmarks US2 (T028, FR-037)
  describe('partners and opponents', () => {
    const withRows = (): MemberMatchRecordsResponse => ({
      ...oneMatch,
      doubles_matches: 6,
      partner_records: [
        {
          player_key: 'm:p1',
          member_id: 'p1',
          nickname: '阿哲',
          wins: 4,
          losses: 2,
          matches: 6,
          win_rate: 0.6667,
          avg_margin: 2.5,
          low_sample: false,
        },
      ],
    });

    it("shows the friend's tables, with rows that cannot be clicked", () => {
      const { fixture } = setup({ getFriendMatchRecords: () => of(withRows()) });
      const root: HTMLElement = fixture.nativeElement;

      expect(root.querySelectorAll('app-matchup-records').length).toBe(2);
      expect(root.querySelector('[data-role="partner"] [data-player="m:p1"]')).not.toBeNull();
      expect(root.querySelector('app-matchup-records button.matchup--button')).toBeNull();
    });

    it('still has no filter form of its own', () => {
      const { fixture } = setup({ getFriendMatchRecords: () => of(withRows()) });
      expect(fixture.nativeElement.querySelector('form')).toBeNull();
      expect(fixture.nativeElement.querySelector('[data-picked-player]')).toBeNull();
    });

    it("a matchup sentence leads to that player's row", () => {
      const { fixture } = setup({
        getFriendMatchRecords: () => of(withRows()),
        getFriendMatchDashboard: () =>
          of(
            dashboardFixture({
              insights: insightsFixture({
                matchups: [
                  insightFixture({
                    list: 'matchup',
                    rule: 'partner_above_overall',
                    metric_key: null,
                    player: { key: 'm:p1', nickname: '阿哲', member_id: 'p1' },
                    params: { win_rate: 0.67, matches: 6, wins: 4, losses: 2, baseline: 0.4, diff: 0.27 },
                  }),
                ],
              }),
            }),
          ),
      });
      const root: HTMLElement = fixture.nativeElement;
      document.body.appendChild(root);

      root.querySelector<HTMLButtonElement>('app-player-insights [data-list="matchup"] .insight')!.click();

      expect(document.activeElement).toBe(root.querySelector('#matchup-partner-m\\:p1'));
      root.remove();
    });

    it('shows no tables for a friend without any match', () => {
      const { fixture } = setup({ getFriendMatchRecords: () => of(emptyRecords) });
      expect(fixture.nativeElement.querySelector('app-matchup-records')).toBeNull();
    });
  });

  // 036-match-insights-benchmarks US1 (T015, FR-037)
  describe('strengths and weaknesses summary', () => {
    const withSummary = () =>
      of(
        dashboardFixture({
          insights: insightsFixture({
            weaknesses: [insightFixture({ list: 'weakness', metric_key: 'winner_share' })],
          }),
        }),
      );

    it("shows the friend's whole summary, things to work on included, above their dashboard", () => {
      const { fixture } = setup({ getFriendMatchDashboard: withSummary });
      const root: HTMLElement = fixture.nativeElement;

      const summary = root.querySelector('app-player-insights')!;
      const dashboard = root.querySelector('app-player-dashboard')!;
      expect(summary.compareDocumentPosition(dashboard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(summary.querySelector('[data-list="weakness"] [data-sentence]')).not.toBeNull();
    });

    it("jumps to the friend's metric card", () => {
      const { fixture } = setup({ getFriendMatchDashboard: withSummary });
      const root: HTMLElement = fixture.nativeElement;
      document.body.appendChild(root);

      root.querySelector<HTMLButtonElement>('app-player-insights .insight')!.click();

      expect(root.querySelector<HTMLDetailsElement>('[data-group="ending"]')!.open).toBe(true);
      expect(document.activeElement).toBe(root.querySelector('#metric-winner_share'));
      root.remove();
    });

    it('shows nothing of the summary when the dashboard is refused', () => {
      const { fixture } = setup({
        getFriendMatchDashboard: () =>
          throwError(
            () =>
              ({
                errorCode: 'MATCH_RECORDS_PRIVATE',
                i18nKey: 'errors.MATCH_RECORDS_PRIVATE',
                detail: null,
                status: 403,
              }) satisfies ApiError,
          ),
      });
      expect(fixture.nativeElement.querySelector('app-player-insights')).toBeNull();
    });
  });
});
