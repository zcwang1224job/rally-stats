import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { Observable, of, throwError } from 'rxjs';
import { MemberMatchRecordsResponse } from '../../../core/api/group-member-view.models';
import { InviteCandidatesResponse } from '../../../core/api/friend.models';
import { MemberMatchDashboardResponse } from '../../../core/api/player-dashboard.models';
import { dashboardFixture } from '../../../core/player-dashboard/dashboard-fixtures';
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
  opponent_records: [{ nickname: '小華', wins: 1, losses: 0, matches: 1, win_rate: 1 }],
  page: 1,
  total_pages: 1,
};

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
  } = {},
) {
  TestBed.configureTestingModule({
    imports: [MatchHistoryComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: AuthService,
        useValue: {
          getMatchRecords: () => of(options.records ?? recordsResponse),
          getMatchDashboard: (...args: unknown[]) => {
            options.dashboardCalls?.push(args);
            return options.dashboard ?? of(dashboardFixture());
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
      expect(fixture.nativeElement.querySelectorAll('app-player-dashboard [data-metric]').length).toBe(18);
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
    });
  });
});
