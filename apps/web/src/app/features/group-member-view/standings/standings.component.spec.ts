import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { GroupStandingsResponse } from '../../../core/api/group-member-view.models';
import { GroupMemberViewService } from '../group-member-view.service';
import { StandingsComponent } from './standings.component';

const standingsResponse: GroupStandingsResponse = {
  current_round_number: 3,
  rounds: [1, 2],
  members: [
    {
      // Round-robin singles: multiple matches in one round — 1 win, 1 loss.
      roster_entry_id: 'r1',
      nickname: '小明',
      current_status: 'active',
      rounds: {
        '1': { wins: 0, losses: 0, left: false },
        '2': { wins: 1, losses: 1, left: false },
      },
    },
    {
      roster_entry_id: 'r2',
      nickname: '小華',
      current_status: 'left',
      rounds: {
        '1': { wins: 1, losses: 0, left: false },
        '2': { wins: 0, losses: 0, left: true },
      },
    },
  ],
};

function setup(response: GroupStandingsResponse = standingsResponse) {
  TestBed.configureTestingModule({
    imports: [StandingsComponent],
    providers: [
      provideTranslateService({}),
      { provide: GroupMemberViewService, useValue: { getStandings: () => of(response) } },
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
    const [player1, player2] = standingsResponse.members;

    expect(fixture.componentInstance.hasRecord(player1, 1)).toBe(false); // did_not_play
    expect(fixture.componentInstance.hasRecord(player1, 2)).toBe(true); // 1-1
    expect(fixture.componentInstance.hasRecord(player2, 1)).toBe(true); // 1-0
    expect(fixture.componentInstance.hasRecord(player2, 2)).toBe(false); // left
  });

  it('totalRecord sums wins and losses across every round', () => {
    const fixture = setup();
    const [player1, player2] = standingsResponse.members;

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
    expect(dataStatuses).toContain('left');
    expect(dataStatuses).toContain('did_not_play');
  });

  it('shows a total-record column for every member', () => {
    const fixture = setup();

    expect(fixture.nativeElement.querySelectorAll('.total-record').length).toBe(2);
  });
});
