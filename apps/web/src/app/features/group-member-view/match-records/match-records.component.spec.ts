import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { GroupMatchRecordsResponse } from '../../../core/api/group-member-view.models';
import { GroupMemberViewService } from '../group-member-view.service';
import { MatchRecordsComponent } from './match-records.component';

const recordsResponse: GroupMatchRecordsResponse = {
  matches: [
    {
      match_id: 'm1',
      round_number: 1,
      team_a: [
        { roster_entry_id: 'p1', nickname: '小明', team: 'A' },
        { roster_entry_id: 'p2', nickname: '小華', team: 'A' },
      ],
      team_b: [
        { roster_entry_id: 'p3', nickname: '小美', team: 'B' },
        { roster_entry_id: 'p4', nickname: '小強', team: 'B' },
      ],
      score_a: 21,
      score_b: 15,
      winner_team: 'A',
      started_at: '2026-01-01T10:00:00Z',
      ended_at: '2026-01-01T10:15:00Z',
    },
    {
      match_id: 'm2',
      round_number: 2,
      team_a: [{ roster_entry_id: 'p1', nickname: '小明', team: 'A' }],
      team_b: [{ roster_entry_id: 'p3', nickname: '小美', team: 'B' }],
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

function setup(
  response: GroupMatchRecordsResponse = recordsResponse,
  detailCalls: unknown[][] = [],
) {
  TestBed.configureTestingModule({
    imports: [MatchRecordsComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: GroupMemberViewService,
        useValue: {
          getMatchRecords: () => of(response),
          getMatchRecordDetail: (...args: unknown[]) => {
            detailCalls.push(args);
            return of(null);
          },
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(MatchRecordsComponent);
  fixture.componentRef.setInput('groupId', 'g1');
  fixture.detectChanges();
  return fixture;
}

describe('MatchRecordsComponent winner-by-name', () => {
  it('names the winning side\'s players when team A won', () => {
    const fixture = setup();

    expect(fixture.componentInstance.winnerNames(recordsResponse.matches[0])).toBe('小明、小華');
  });

  it('names the winning side\'s players when team B won', () => {
    const fixture = setup();

    expect(fixture.componentInstance.winnerNames(recordsResponse.matches[1])).toBe('小美');
  });

  it('renders the winner label with player names, not "A方"/"B方"', () => {
    const fixture = setup();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', {
      groupMemberView: { matchRecords: { winnerLabel: '{{names}} 獲勝' } },
    });
    translate.use('en');
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('小明、小華 獲勝');
    expect(text).not.toContain('A 方');
    expect(text).not.toContain('B 方');
  });
});

describe('MatchRecordsComponent start/end time', () => {
  it('shows a time range for a match with both timestamps', () => {
    const fixture = setup();

    const items = fixture.nativeElement.querySelectorAll('.record-list li');
    const firstTimeRange = items[0].querySelector('.time-range');
    expect(firstTimeRange).not.toBeNull();
    expect(firstTimeRange.textContent).toContain(':'); // some HH:mm was rendered
    expect(firstTimeRange.textContent).toContain('-');
  });

  it('shows no time range when either timestamp is missing', () => {
    const fixture = setup();

    const items = fixture.nativeElement.querySelectorAll('.record-list li');
    expect(items[1].querySelector('.time-range')).toBeNull();
  });
});

// 016-match-score-timeline (US1, T015a regression guard for I1): this is
// the ONE entry point that should call the group-scoped, active-membership
// endpoint — contrast with match-history/group-history, which must call
// AuthService instead (research.md #1/#4).
describe('MatchRecordsComponent match detail', () => {
  it('clicking a row calls GroupMemberViewService.getMatchRecordDetail with groupId and matchId', () => {
    const detailCalls: unknown[][] = [];
    const fixture = setup(recordsResponse, detailCalls);

    const row = fixture.nativeElement.querySelectorAll('.record-list li')[0] as HTMLElement;
    row.click();

    expect(detailCalls.length).toBe(1);
    expect(detailCalls[0]).toEqual(['g1', 'm1']);
  });
});
