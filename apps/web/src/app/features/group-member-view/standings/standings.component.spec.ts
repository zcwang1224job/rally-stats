import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { Observable, of } from 'rxjs';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { GroupStandingsResponse } from '../../../core/api/group-member-view.models';
import { GroupMemberViewService } from '../group-member-view.service';
import { StandingsComponent } from './standings.component';

// 018-group-leaderboard: `members` arrives pre-sorted/pre-ranked by the
// backend (rank/total_wins/total_losses) — no member here has "left"
// status any more, since FR-008 excludes such members from the response
// entirely (they used to show a `left: true` row; see backend
// test_standings_formula.py's removal note for the equivalent backend-side
// change).
const standingsResponse: GroupStandingsResponse = {
  current_round_number: 3,
  rounds: [1, 2],
  members: [
    {
      roster_entry_id: 'r2',
      nickname: '小華',
      current_status: 'active',
      rounds: {
        '1': { wins: 1, losses: 0, left: false },
        '2': { wins: 0, losses: 0, left: false },
      },
      rank: 1,
      total_wins: 1,
      total_losses: 0,
    },
    {
      // Round-robin singles: multiple matches in one round — 1 win, 1 loss.
      roster_entry_id: 'r1',
      nickname: '小明',
      current_status: 'active',
      rounds: {
        '1': { wins: 0, losses: 0, left: false },
        '2': { wins: 1, losses: 1, left: false },
      },
      rank: 2,
      total_wins: 1,
      total_losses: 1,
    },
    {
      roster_entry_id: 'r3',
      nickname: '小張',
      current_status: 'active',
      rounds: {
        '1': { wins: 0, losses: 0, left: false },
        '2': { wins: 0, losses: 0, left: false },
      },
      rank: 3,
      total_wins: 0,
      total_losses: 0,
    },
  ],
};

function setup(
  options: {
    response?: GroupStandingsResponse;
    myRosterEntryId?: string;
  } = {},
) {
  const response = options.response ?? standingsResponse;
  TestBed.configureTestingModule({
    imports: [StandingsComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: RealtimeService,
        useValue: { connectionState: signal('connected'), subscribe: () => of() },
      },
      {
        provide: GroupMemberViewService,
        useValue: {
          getStandings: () => of(response),
          resolveRosterEntryId: (): Observable<string> => of(options.myRosterEntryId ?? 'nobody'),
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(StandingsComponent);
  fixture.componentRef.setInput('groupId', 'g1');
  fixture.detectChanges();
  return fixture;
}

describe('StandingsComponent per-round record (011-round-robin-scheduling)', () => {
  it('hasRecord is true only when a round actually has a win or a loss', () => {
    const fixture = setup();
    const [, player1] = standingsResponse.members; // r1 小明

    expect(fixture.componentInstance.hasRecord(player1, 1)).toBe(false); // did_not_play
    expect(fixture.componentInstance.hasRecord(player1, 2)).toBe(true); // 1-1
  });

  it('totalRecord reflects the backend-computed total_wins/total_losses', () => {
    const fixture = setup();
    const [player2, player1] = standingsResponse.members;

    expect(fixture.componentInstance.totalRecord(player1)).toEqual({ wins: 1, losses: 1 });
    expect(fixture.componentInstance.totalRecord(player2)).toEqual({ wins: 1, losses: 0 });
  });

  it('renders a round with both a win and a loss as "mixed", not won or lost', () => {
    const fixture = setup();

    const badges = fixture.nativeElement.querySelectorAll(
      '.status-badge',
    ) as NodeListOf<HTMLElement>;
    const dataStatuses = Array.from(badges).map((b) => b.getAttribute('data-status'));
    expect(dataStatuses).toContain('mixed');
    expect(dataStatuses).toContain('did_not_play');
  });

  it('shows a total-record column for every member', () => {
    const fixture = setup();

    expect(fixture.nativeElement.querySelectorAll('.total-record').length).toBe(3);
  });
});

describe('StandingsComponent — 018-group-leaderboard', () => {
  it('renders members in the backend-provided rank order without re-sorting', () => {
    const fixture = setup();

    const nicknames = Array.from(
      fixture.nativeElement.querySelectorAll('tbody tr td:nth-child(2)') as NodeListOf<HTMLElement>,
    ).map((cell) => cell.textContent?.trim().split('\n')[0]?.trim());
    // 小華 (rank 1) before 小明 (rank 2) before 小張 (rank 3) — matches the
    // order already in `standingsResponse.members`, i.e. the component
    // never reorders what the backend returned.
    expect(nicknames[0]).toContain('小華');
    expect(nicknames[1]).toContain('小明');
    expect(nicknames[2]).toContain('小張');
  });

  it('renders each rank number from the backend, not computed client-side', () => {
    const fixture = setup();

    const rankCells = Array.from(
      fixture.nativeElement.querySelectorAll('tbody tr td:nth-child(1)') as NodeListOf<HTMLElement>,
    ).map((cell) => cell.textContent?.trim());
    expect(rankCells.length).toBe(3);
    for (const cell of rankCells) {
      expect(cell).toContain('rankValue');
    }
  });

  it('marks the viewer\'s own row with a non-color self badge (FR-011)', () => {
    const fixture = setup({ myRosterEntryId: 'r1' });

    expect(fixture.componentInstance.isSelf(standingsResponse.members[1])).toBe(true);
    expect(fixture.componentInstance.isSelf(standingsResponse.members[0])).toBe(false);

    const selfRow = fixture.nativeElement.querySelector('tr.is-self') as HTMLElement | null;
    expect(selfRow).toBeTruthy();
    expect(selfRow?.querySelector('.self-badge')).toBeTruthy();
  });

  it('shows "尚無比賽紀錄" instead of "0 勝 0 敗" for a member with no completed matches (FR-007)', () => {
    const fixture = setup();

    expect(fixture.componentInstance.hasNoRecordYet(standingsResponse.members[2])).toBe(true);
    expect(fixture.componentInstance.hasNoRecordYet(standingsResponse.members[0])).toBe(false);

    const totalCells = fixture.nativeElement.querySelectorAll('.total-record');
    const lastCell = totalCells[totalCells.length - 1] as HTMLElement;
    expect(lastCell.textContent).toContain('noRecordYet');
  });
});
