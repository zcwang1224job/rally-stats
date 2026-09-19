import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { signal } from '@angular/core';
import { of, EMPTY } from 'rxjs';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../../core/realtime/reconnect-refetch.service';
import { CourtControlComponent } from './court-control.component';
import { ScheduleService } from './schedule.service';
import { CourtScheduleStatus } from './schedule.models';

function realtimeStub() {
  return { connectionState: signal('connected'), subscribe: () => EMPTY };
}

function reconnectStub() {
  return { onReconnect: () => EMPTY };
}

const doublesServe = {
  server_roster_entry_id: 'p1',
  server_team: 'A' as const,
  team_a_right_roster_entry_id: 'p1',
  team_a_left_roster_entry_id: 'p2',
  team_b_right_roster_entry_id: 'p3',
  team_b_left_roster_entry_id: 'p4',
};

const court: CourtScheduleStatus = {
  court_id: 'c1',
  name: '1號場',
  waiting_reason: null,
  next_up: null,
  current_match: {
    match_id: 'm1',
    status: 'in_progress',
    score_a: 5,
    score_b: 7,
    participants: [
      { roster_entry_id: 'p1', nickname: '陳甲', team: 'A' },
      { roster_entry_id: 'p2', nickname: '劉乙', team: 'A' },
      { roster_entry_id: 'p3', nickname: '徐丙', team: 'B' },
      { roster_entry_id: 'p4', nickname: '李丁', team: 'B' },
    ],
    serve: doublesServe,
  },
};

function setup(overrideCourt: CourtScheduleStatus = court) {
  TestBed.configureTestingModule({
    imports: [CourtControlComponent],
    providers: [
      provideTranslateService({}),
      { provide: RealtimeService, useFactory: realtimeStub },
      { provide: ReconnectRefetchService, useFactory: reconnectStub },
      { provide: ScheduleService, useValue: { scoreMatch: () => of({}), endMatch: () => of({}) } },
    ],
  });
  const fixture = TestBed.createComponent(CourtControlComponent);
  fixture.componentRef.setInput('groupId', 'g1');
  fixture.componentRef.setInput('court', overrideCourt);
  fixture.detectChanges();
  return fixture;
}

/** Teams face each other across the net, so each team's own right/left
 * service court sits on OPPOSITE physical sidelines (see
 * ScoreboardComponent.html's comment) — team A: left→top, right→bottom;
 * team B: right→top, left→bottom. This mapping must follow team IDENTITY,
 * not which screen half currently renders that team, since toggleSwap()
 * only moves a team sideways and never changes which direction it faces. */
describe("CourtControlComponent mirrors each team's own left/right service court (station top/bottom)", () => {
  // toggleSwap() persists the preference per court (localStorage); start
  // every test here unswapped so no test depends on the order they run in.
  beforeEach(() => localStorage.clear());

  it('unswapped: team A top=left-court player, bottom=right-court player; team B mirrored', () => {
    const fixture = setup();

    const teamA = fixture.nativeElement.querySelector('.team--a');
    const teamB = fixture.nativeElement.querySelector('.team--b');
    expect(teamA.querySelector('.station--top').textContent).toContain('劉乙'); // team_a_left
    expect(teamA.querySelector('.station--bottom').textContent).toContain('陳甲'); // team_a_right
    expect(teamB.querySelector('.station--top').textContent).toContain('徐丙'); // team_b_right
    expect(teamB.querySelector('.station--bottom').textContent).toContain('李丁'); // team_b_left
  });

  it('swapped: the whole court turns around, so each team\'s right court changes slot', () => {
    const fixture = setup();
    fixture.componentInstance.toggleSwap();
    fixture.detectChanges();

    // Team B now plays from the left (right court at the bottom), team A
    // from the right (right court at the top).
    const teamA = fixture.nativeElement.querySelector('.team--a');
    const teamB = fixture.nativeElement.querySelector('.team--b');
    expect(teamB.querySelector('.station--top').textContent).toContain('李丁'); // team_b_left
    expect(teamB.querySelector('.station--bottom').textContent).toContain('徐丙'); // team_b_right
    expect(teamA.querySelector('.station--top').textContent).toContain('陳甲'); // team_a_right
    expect(teamA.querySelector('.station--bottom').textContent).toContain('劉乙'); // team_a_left
  });

  it('truncates a long nickname to its first 2 characters, keeping the full name as the pill\'s aria-label', () => {
    const fixture = setup({
      ...court,
      current_match: {
        ...court.current_match!,
        participants: [
          { roster_entry_id: 'p1', nickname: '陳大文豪', team: 'A' },
          { roster_entry_id: 'p2', nickname: '劉乙', team: 'A' },
          { roster_entry_id: 'p3', nickname: '徐丙', team: 'B' },
          { roster_entry_id: 'p4', nickname: '李丁', team: 'B' },
        ],
      },
    });

    const station = fixture.nativeElement.querySelector('.team--a .station--bottom'); // team_a_right = p1
    expect(station.textContent).toContain('陳大');
    expect(station.textContent).not.toContain('陳大文豪');
    expect(station.getAttribute('aria-label')).toBe('陳大文豪');
  });
});
