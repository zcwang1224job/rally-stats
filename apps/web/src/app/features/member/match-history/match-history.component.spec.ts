import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { MemberMatchRecordsResponse } from '../../../core/api/group-member-view.models';
import { AuthService } from '../../auth/auth.service';
import { MatchHistoryComponent } from './match-history.component';

const recordsResponse: MemberMatchRecordsResponse = {
  matches: [
    {
      match_id: 'm1',
      round_number: 1,
      group_id: 'g1',
      group_name: '週三團',
      won: true,
      team_a: [{ roster_entry_id: 'p1', nickname: '小明', team: 'A' }],
      team_b: [{ roster_entry_id: 'p2', nickname: '小華', team: 'B' }],
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

function setup(detailCalls: unknown[][] = []) {
  TestBed.configureTestingModule({
    imports: [MatchHistoryComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: AuthService,
        useValue: {
          getMatchRecords: () => of(recordsResponse),
          getMatchRecordDetail: (...args: unknown[]) => {
            detailCalls.push(args);
            return of(null);
          },
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
});
