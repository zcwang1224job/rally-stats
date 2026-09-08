import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { MemberGroupHistoryResponse } from '../../../../core/api/friend.models';
import { FriendsService } from '../../../friends/friends.service';
import { GroupHistoryComponent } from './group-history.component';

const historyResponse: MemberGroupHistoryResponse = {
  group_id: 'g1',
  group_name: '週三團',
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
};

function setup(overrides: { getMemberGroupHistory?: (...args: unknown[]) => unknown } = {}) {
  const calls: unknown[][] = [];
  const getMemberGroupHistory =
    overrides.getMemberGroupHistory ??
    ((...args: unknown[]) => {
      calls.push(args);
      return of(historyResponse);
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
    ],
  });
  const fixture = TestBed.createComponent(GroupHistoryComponent);
  return { fixture, calls };
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
    const [, , nickname] = calls[0] as [string, number, string | undefined];
    expect(nickname).toBe('小華');
  });

  it('clearFilters resets the form and re-fetches with no nickname', () => {
    const { fixture, calls } = setup();
    fixture.detectChanges();
    fixture.componentInstance.filterForm.controls.nickname.setValue('小華');
    fixture.componentInstance.applyFilters();
    calls.length = 0;

    fixture.componentInstance.clearFilters();

    expect(calls.length).toBe(1);
    const [, , nickname] = calls[0] as [string, number, string | undefined];
    expect(nickname).toBeUndefined();
  });
});
