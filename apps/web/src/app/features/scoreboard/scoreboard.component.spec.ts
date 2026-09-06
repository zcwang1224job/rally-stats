import { convertToParamMap, ActivatedRoute } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, EMPTY } from 'rxjs';
import { signal } from '@angular/core';
import { CourtControlService } from '../../core/api/court-control.service';
import { LinkHeartbeatService } from '../../core/api/link-heartbeat.service';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../core/realtime/reconnect-refetch.service';
import { ScoreboardComponent } from './scoreboard.component';

const courtInfo = {
  court_id: 'c1',
  group_id: 'g1',
  name: '1號場',
  link_type: 'scoreboard' as const,
  link_version: 0,
  deleted: false,
  group_disbanded: false,
};

function realtimeStub(connected = true) {
  return { connectionState: signal(connected ? 'connected' : 'disconnected'), subscribe: () => EMPTY };
}

function reconnectStub() {
  return { onReconnect: () => EMPTY };
}

function setup(courtState: unknown, connected = true) {
  TestBed.configureTestingModule({
    imports: [ScoreboardComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: convertToParamMap({ courtToken: 'tok' }) } },
      },
      { provide: LinkHeartbeatService, useValue: { watchCourtLink: () => of(courtInfo) } },
      { provide: RealtimeService, useFactory: () => realtimeStub(connected) },
      { provide: ReconnectRefetchService, useFactory: reconnectStub },
      { provide: CourtControlService, useValue: { getState: () => of(courtState) } },
    ],
  });
  const fixture = TestBed.createComponent(ScoreboardComponent);
  fixture.detectChanges();
  return fixture;
}

describe('ScoreboardComponent', () => {
  it('doubles match: each team panel shows both participants stacked', () => {
    const fixture = setup({
      court_id: 'c1',
      round_number: 1,
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
      },
      waiting_reason: null,
      next_up: null,
    });

    const teamA = fixture.nativeElement.querySelector('.team--a');
    const teamB = fixture.nativeElement.querySelector('.team--b');
    expect(teamA.textContent).toContain('陳甲');
    expect(teamA.textContent).toContain('劉乙');
    expect(teamB.textContent).toContain('徐丙');
    expect(teamB.textContent).toContain('李丁');
    expect(teamA.querySelector('.score').textContent).toContain('5');
    expect(teamB.querySelector('.score').textContent).toContain('7');
  });

  it('singles match: each team panel shows exactly one participant', () => {
    const fixture = setup({
      court_id: 'c1',
      round_number: 1,
      current_match: {
        match_id: 'm1',
        status: 'in_progress',
        score_a: 1,
        score_b: 2,
        participants: [
          { roster_entry_id: 'p1', nickname: '陳甲', team: 'A' },
          { roster_entry_id: 'p2', nickname: '徐丙', team: 'B' },
        ],
      },
      waiting_reason: null,
      next_up: null,
    });

    const teamA = fixture.nativeElement.querySelector('.team--a');
    expect(teamA.querySelectorAll('.names div').length).toBe(1);
  });

  it('shows the next-up badge when next_up is present', () => {
    const fixture = setup({
      court_id: 'c1',
      round_number: 1,
      current_match: null,
      waiting_reason: null,
      next_up: {
        participants: [
          { roster_entry_id: 'p1', nickname: '王戊', team: 'A' },
          { roster_entry_id: 'p2', nickname: '林己', team: 'B' },
        ],
      },
    });

    expect(fixture.nativeElement.querySelector('.next-up')).not.toBeNull();
  });

  it('does not show the next-up badge when next_up is absent', () => {
    const fixture = setup({
      court_id: 'c1',
      round_number: 1,
      current_match: null,
      waiting_reason: null,
      next_up: null,
    });

    expect(fixture.nativeElement.querySelector('.next-up')).toBeNull();
  });

  it('shows the offline banner when disconnected', () => {
    const fixture = setup(
      { court_id: 'c1', round_number: 1, current_match: null, waiting_reason: null, next_up: null },
      false,
    );

    expect(fixture.nativeElement.querySelector('.offline-banner')).not.toBeNull();
  });
});
