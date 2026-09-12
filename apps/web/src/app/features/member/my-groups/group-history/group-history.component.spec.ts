import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { MemberGroupHistoryFilters, MemberGroupHistoryResponse } from '../../../../core/api/friend.models';
import { AuthService } from '../../../auth/auth.service';
import { FriendsService } from '../../../friends/friends.service';
import { GroupHistoryComponent } from './group-history.component';

const historyResponse: MemberGroupHistoryResponse = {
  group_id: 'g1',
  group_name: '週三團',
  final_standings: [
    {
      roster_entry_id: 'p1',
      nickname: '小明',
      current_status: 'active',
      is_self: true,
      rank: 1,
      total_matches: 1,
      total_wins: 1,
      total_losses: 0,
    },
    {
      roster_entry_id: 'p2',
      nickname: '小華',
      current_status: 'left',
      is_self: false,
      rank: 2,
      total_matches: 1,
      total_wins: 0,
      total_losses: 1,
    },
    {
      roster_entry_id: 'p5',
      nickname: '小強',
      current_status: 'kicked',
      is_self: false,
      rank: 3,
      total_matches: 0,
      total_wins: 0,
      total_losses: 0,
    },
  ],
  my_stats: {
    total_matches: 1,
    total_wins: 1,
    total_losses: 0,
    win_rate: 1,
    round_win_rates: [{ round_number: 1, wins: 1, losses: 0, win_rate: 1 }],
    opponent_records: [{ nickname: '小華', wins: 1, losses: 0, matches: 1, win_rate: 1 }],
  },
  matches: [
    {
      match_id: 'm1',
      round_number: 1,
      team_a: [{ roster_entry_id: 'p1', nickname: '小明', team: 'A' }],
      team_b: [{ roster_entry_id: 'p2', nickname: '小華', team: 'B' }],
      score_a: 21,
      score_b: 15,
      winner_team: 'A',
      started_at: '2026-01-01T10:00:00Z',
      ended_at: '2026-01-01T10:15:00Z',
    },
    {
      match_id: 'm2',
      round_number: 2,
      team_a: [{ roster_entry_id: 'p3', nickname: '路人甲', team: 'A' }],
      team_b: [{ roster_entry_id: 'p4', nickname: '路人乙', team: 'B' }],
      score_a: 10,
      score_b: 21,
      winner_team: 'B',
      started_at: null,
      ended_at: null,
    },
  ],
  page: 1,
  total_pages: 1,
  player_records: [
    { nickname: '小明', wins: 1, losses: 0, matches: 1, win_rate: 1 },
    { nickname: '小華', wins: 0, losses: 1, matches: 1, win_rate: 0 },
    { nickname: '路人乙', wins: 1, losses: 0, matches: 1, win_rate: 1 },
    { nickname: '路人甲', wins: 0, losses: 1, matches: 1, win_rate: 0 },
  ],
};

function setup(
  overrides: {
    getMemberGroupHistory?: (...args: unknown[]) => unknown;
    getMatchRecordDetail?: (...args: unknown[]) => unknown;
  } = {},
) {
  const calls: unknown[][] = [];
  const getMemberGroupHistory =
    overrides.getMemberGroupHistory ??
    ((...args: unknown[]) => {
      calls.push(args);
      return of(historyResponse);
    });
  const matchRecordDetailCalls: unknown[][] = [];
  const getMatchRecordDetail =
    overrides.getMatchRecordDetail ??
    ((...args: unknown[]) => {
      matchRecordDetailCalls.push(args);
      return of(null);
    });
  TestBed.configureTestingModule({
    imports: [GroupHistoryComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: convertToParamMap({ groupId: 'g1' }) } },
      },
      { provide: FriendsService, useValue: { getMemberGroupHistory } },
      { provide: AuthService, useValue: { getMatchRecordDetail } },
    ],
  });
  const fixture = TestBed.createComponent(GroupHistoryComponent);
  return { fixture, calls, matchRecordDetailCalls };
}

describe('GroupHistoryComponent', () => {
  it('renders the group name, the personal-stats hero card, and the group-wide match list — including matches the viewer did not play', () => {
    const { fixture } = setup();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.page-title').textContent).toContain('週三團');
    // Both matches show, even though the second involves neither "me" by
    // construction in this fixture — the list is group-wide, not personal.
    expect(fixture.nativeElement.querySelectorAll('.record-list li').length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('100%'); // my_stats win-rate ring
  });

  it('renders a pie-chart legend row for every player in player_records, with win count and win rate', () => {
    const { fixture } = setup();
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('.player-pie-card__legend-row');
    expect(rows.length).toBe(4);
    const text = fixture.nativeElement.querySelector('.player-pie-card').textContent;
    expect(text).toContain('小明');
    expect(text).toContain('1');
    expect(text).toContain('100%');
    expect(text).toContain('小華');
    expect(text).toContain('0%');
  });

  it('shows the pie-chart empty state when the filtered result has no matches', () => {
    const { fixture } = setup({
      getMemberGroupHistory: () =>
        of({
          ...historyResponse,
          matches: [],
          player_records: [],
          my_stats: {
            total_matches: 0,
            total_wins: 0,
            total_losses: 0,
            win_rate: 0,
            round_win_rates: [],
            opponent_records: [],
          },
        }),
    });
    fixture.detectChanges();

    expect(fixture.componentInstance.playerPieSlices()).toEqual([]);
    expect(fixture.nativeElement.querySelector('.player-pie-card').textContent).toContain(
      'memberGroupHistory.filters.playerChartEmpty',
    );
  });

  it('renders the round-trend chart and opponent leaderboard from my_stats', () => {
    const { fixture } = setup();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.trend-chart')).not.toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.ranking-row').length).toBe(1);
    expect(fixture.nativeElement.querySelector('.ranking-row__name').textContent).toContain(
      '小華',
    );
  });

  it('shows the empty-state message when there are no matches at all', () => {
    const { fixture } = setup({
      getMemberGroupHistory: () =>
        of({
          ...historyResponse,
          matches: [],
          player_records: [],
          my_stats: {
            total_matches: 0,
            total_wins: 0,
            total_losses: 0,
            win_rate: 0,
            round_win_rates: [],
            opponent_records: [],
          },
        }),
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('memberGroupHistory.empty');
  });

  it('shows an error instead of the shell when the request fails', () => {
    const { fixture } = setup({
      getMemberGroupHistory: () =>
        throwError(() => ({
          i18nKey: 'errors.GROUP_MEMBERSHIP_NEVER_HELD',
          errorCode: 'GROUP_MEMBERSHIP_NEVER_HELD',
        })),
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('errors.GROUP_MEMBERSHIP_NEVER_HELD');
  });

  it('submitting the nickname filter re-fetches with that nickname, searching the whole group', () => {
    const { fixture, calls } = setup();
    fixture.detectChanges();
    calls.length = 0; // clear the initial load call

    fixture.componentInstance.filterForm.controls.nickname.setValue('小華');
    fixture.componentInstance.applyFilters();

    expect(calls.length).toBe(1);
    const [, , filters] = calls[0] as [string, number, MemberGroupHistoryFilters];
    expect(filters.nickname).toBe('小華');
  });

  it('submitting the advanced round-range filters re-fetches with them applied', () => {
    const { fixture, calls } = setup();
    fixture.detectChanges();
    calls.length = 0;

    fixture.componentInstance.filterForm.patchValue({ round_from: '2', round_to: '4' });
    fixture.componentInstance.applyFilters();

    expect(calls.length).toBe(1);
    const [, , filters] = calls[0] as [string, number, MemberGroupHistoryFilters];
    expect(filters.round_from).toBe(2);
    expect(filters.round_to).toBe(4);
  });

  it('submitting the group1/group2 nickname filters re-fetches with up to two names per group', () => {
    const { fixture, calls } = setup();
    fixture.detectChanges();
    calls.length = 0;

    fixture.componentInstance.filterForm.patchValue({
      group1_player1: 'Alice',
      group1_player2: 'Bob',
      group2_player1: 'Carol',
    });
    fixture.componentInstance.applyFilters();

    expect(calls.length).toBe(1);
    const [, , filters] = calls[0] as [string, number, MemberGroupHistoryFilters];
    expect(filters.group1_player1).toBe('Alice');
    expect(filters.group1_player2).toBe('Bob');
    expect(filters.group2_player1).toBe('Carol');
    expect(filters.group2_player2).toBeUndefined();
  });

  it('submitting the team A/B score comparisons re-fetches with them applied', () => {
    const { fixture, calls } = setup();
    fixture.detectChanges();
    calls.length = 0;

    fixture.componentInstance.filterForm.patchValue({
      score_a_cmp: 'gt',
      score_a: '20',
      score_b_cmp: 'eq',
      score_b: '15',
    });
    fixture.componentInstance.applyFilters();

    expect(calls.length).toBe(1);
    const [, , filters] = calls[0] as [string, number, MemberGroupHistoryFilters];
    expect(filters.score_a_cmp).toBe('gt');
    expect(filters.score_a).toBe(20);
    expect(filters.score_b_cmp).toBe('eq');
    expect(filters.score_b).toBe(15);
  });

  it('the "clear filters" button only appears once a filter has actually been applied', () => {
    const { fixture } = setup();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.filters-actions .btn--secondary')).toBeNull();

    fixture.componentInstance.filterForm.controls.nickname.setValue('小華');
    fixture.componentInstance.applyFilters();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.filters-actions .btn--secondary')).not.toBeNull();
  });

  it('clearFilters resets the form and re-fetches with no filters, hiding the clear button again', () => {
    const { fixture, calls } = setup();
    fixture.detectChanges();
    fixture.componentInstance.filterForm.controls.nickname.setValue('小華');
    fixture.componentInstance.applyFilters();
    calls.length = 0;

    fixture.componentInstance.clearFilters();
    fixture.detectChanges();

    expect(calls.length).toBe(1);
    const [, , filters] = calls[0] as [string, number, MemberGroupHistoryFilters];
    expect(filters.nickname).toBeUndefined();
    expect(filters.round_from).toBeUndefined();
    expect(filters.group1_player1).toBeUndefined();
    expect(filters.score_a_cmp).toBeUndefined();
    expect(fixture.nativeElement.querySelector('.filters-actions .btn--secondary')).toBeNull();
  });

  // 016-match-score-timeline (regression guard for the I1 finding from
  // /speckit-analyze): this page MUST call AuthService's "ever a member"
  // endpoint, never GroupMemberViewService's active-membership one — a
  // member who left/was kicked from the group must still be able to open
  // a match's detail from here.
  it('clicking a match row calls AuthService.getMatchRecordDetail with only the matchId', () => {
    const { fixture, matchRecordDetailCalls } = setup();
    fixture.detectChanges();

    const row = fixture.nativeElement.querySelectorAll('.record-list li')[0] as HTMLElement;
    row.click();

    expect(matchRecordDetailCalls.length).toBe(1);
    expect(matchRecordDetailCalls[0]).toEqual(['m1']);
  });

  // 019-group-final-standings (T015)
  it('renders final_standings rows in the pre-sorted rank order from the server', () => {
    const { fixture } = setup();
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('.final-standings tbody tr');
    expect(rows.length).toBe(3);
    expect(rows[0].textContent).toContain('小明');
    expect(rows[1].textContent).toContain('小華');
    expect(rows[2].textContent).toContain('小強');
  });

  it('marks only the is_self row with the self badge and highlight class', () => {
    const { fixture } = setup();
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('.final-standings tbody tr');
    expect(rows[0].classList.contains('is-self')).toBe(true);
    expect(rows[0].textContent).toContain('groupMemberView.standings.selfBadge');
    expect(rows[1].classList.contains('is-self')).toBe(false);
    expect(rows[1].textContent).not.toContain('groupMemberView.standings.selfBadge');
  });

  it('shows left/kicked status labels for non-active rows only', () => {
    const { fixture } = setup();
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('.final-standings tbody tr');
    expect(rows[0].textContent).not.toContain('groupMemberView.standings.status.');
    expect(rows[1].textContent).toContain('groupMemberView.standings.status.left');
    expect(rows[2].textContent).toContain('groupMemberView.standings.status.kicked');
  });

  it('shows "尚無比賽紀錄" for a zero-match row instead of "0 勝 0 敗"', () => {
    const { fixture } = setup();
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('.final-standings tbody tr');
    expect(rows[2].textContent).toContain('groupMemberView.standings.noRecordYet');
    expect(rows[0].textContent).toContain('groupMemberView.standings.recordLabel');
  });

  it('shows the whole-block empty message when every row has zero matches', () => {
    const { fixture } = setup({
      getMemberGroupHistory: () =>
        of({
          ...historyResponse,
          final_standings: historyResponse.final_standings.map((row) => ({
            ...row,
            total_matches: 0,
            total_wins: 0,
            total_losses: 0,
          })),
        }),
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.final-standings tbody')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain(
      'member.matchHistory.finalStandings.empty',
    );
  });
});
