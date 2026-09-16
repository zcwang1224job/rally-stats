import { convertToParamMap, ActivatedRoute } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService, TranslateService } from '@ngx-translate/core';
import { of, EMPTY, NEVER, Observable, Subject } from 'rxjs';
import { signal, WritableSignal } from '@angular/core';
import { CourtControlService } from '../../core/api/court-control.service';
import { LinkHeartbeatService } from '../../core/api/link-heartbeat.service';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../core/realtime/reconnect-refetch.service';
import { AuthService } from '../auth/auth.service';
import { ScoreboardComponent } from './scoreboard.component';

const courtInfo = {
  court_id: 'c1',
  group_id: 'g1',
  name: '1號場',
  link_type: 'scoreboard' as const,
  link_version: 0,
  deleted: false,
  group_disbanded: false,
  owner_language: 'en',
};

interface RealtimeStub {
  connectionState: WritableSignal<string>;
  subscribe: (channel: string, event: string) => Observable<{ data: unknown }>;
}

interface ReconnectStub {
  onReconnect: () => Observable<void>;
}

function realtimeStub(connected = true): RealtimeStub {
  return { connectionState: signal(connected ? 'connected' : 'disconnected'), subscribe: () => EMPTY };
}

// 029-serve-rotation-display: lets a test push a message onto exactly one
// named Ably event (e.g. 'match.scoreUpdated') while every other
// subscription still behaves like the plain `realtimeStub` (EMPTY).
function realtimeStubWithEvent(
  event: string,
  subject: Subject<{ data: unknown }>,
  connected = true,
): RealtimeStub {
  return {
    connectionState: signal(connected ? 'connected' : 'disconnected'),
    subscribe: (_channel: string, e: string) => (e === event ? subject : EMPTY),
  };
}

function reconnectStub(): ReconnectStub {
  return { onReconnect: () => EMPTY };
}

function reconnectStubWithTrigger(trigger$: Subject<void>): ReconnectStub {
  return { onReconnect: () => trigger$ };
}

function setup(
  courtState: unknown,
  connected = true,
  courtControl: Partial<CourtControlService> = {},
  linkHeartbeat: { watchCourtLink: () => unknown } = { watchCourtLink: () => of(courtInfo) },
  realtime: RealtimeStub = realtimeStub(connected),
  reconnect: ReconnectStub = reconnectStub(),
) {
  TestBed.configureTestingModule({
    imports: [ScoreboardComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: convertToParamMap({ courtToken: 'tok' }) } },
      },
      { provide: LinkHeartbeatService, useValue: linkHeartbeat },
      { provide: RealtimeService, useValue: realtime },
      { provide: ReconnectRefetchService, useValue: reconnect },
      {
        provide: CourtControlService,
        useValue: { getState: () => of(courtState), ...courtControl },
      },
      {
        provide: AuthService,
        useValue: {
          isLoggedIn: () => false,
          getSupportedLanguages: () => of({ languages: ['zh-TW', 'en'] }),
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(ScoreboardComponent);
  fixture.detectChanges();
  return fixture;
}

const doublesServe = {
  server_roster_entry_id: 'p1',
  server_team: 'A' as const,
  team_a_right_roster_entry_id: 'p1',
  team_a_left_roster_entry_id: 'p2',
  team_b_right_roster_entry_id: 'p3',
  team_b_left_roster_entry_id: 'p4',
};

describe('ScoreboardComponent', () => {
  it('doubles match: each team panel shows both participants, each in their own station', () => {
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
        serve: doublesServe,
      },
      waiting_reason: null,
      next_up: null,
    });

    const teamA = fixture.nativeElement.querySelector('.team--a');
    const teamB = fixture.nativeElement.querySelector('.team--b');
    expect(teamA.querySelectorAll('.station').length).toBe(2);
    expect(teamB.querySelectorAll('.station').length).toBe(2);
    expect(teamA.textContent).toContain('陳甲');
    expect(teamA.textContent).toContain('劉乙');
    expect(teamB.textContent).toContain('徐丙');
    expect(teamB.textContent).toContain('李丁');
    expect(teamA.querySelector('.score').textContent).toContain('5');
    expect(teamB.querySelector('.score').textContent).toContain('7');
  });

  it('singles match: each team panel shows exactly one station, the other stays blank', () => {
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
        serve: {
          server_roster_entry_id: 'p1',
          server_team: 'A',
          team_a_right_roster_entry_id: 'p1',
          team_a_left_roster_entry_id: null,
          team_b_right_roster_entry_id: null,
          team_b_left_roster_entry_id: 'p2',
        },
      },
      waiting_reason: null,
      next_up: null,
    });

    const teamA = fixture.nativeElement.querySelector('.team--a');
    const teamB = fixture.nativeElement.querySelector('.team--b');
    expect(teamA.querySelectorAll('.station').length).toBe(1);
    expect(teamB.querySelectorAll('.station').length).toBe(1);
    expect(teamA.textContent).toContain('陳甲');
    expect(teamB.textContent).toContain('徐丙');
  });

  it('shows a non-color server marker only on the serving station (US1 FR-005)', () => {
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
        serve: doublesServe,
      },
      waiting_reason: null,
      next_up: null,
    });

    const badges = fixture.nativeElement.querySelectorAll('.server-badge');
    expect(badges.length).toBe(1);
    expect(badges[0].textContent.trim().length).toBeGreaterThan(0);
    const serverStation = fixture.nativeElement.querySelector('.station--server');
    expect(serverStation.textContent).toContain('陳甲');
  });

  it('does not render any station when there is no current match (FR-007)', () => {
    const fixture = setup({
      court_id: 'c1',
      round_number: 1,
      current_match: null,
      waiting_reason: 'no_queued_match',
      next_up: null,
    });

    expect(fixture.nativeElement.querySelectorAll('.station').length).toBe(0);
    expect(fixture.nativeElement.querySelector('.server-badge')).toBeNull();
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

  // 018-plan-then-start follow-up
  const scoringMatchState = {
    court_id: 'c1',
    round_number: 1,
    scoreboard_scoring_enabled: true,
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
  };

  it('does not show scoring buttons when scoreboard_scoring_enabled is absent (default)', () => {
    const fixture = setup({ ...scoringMatchState, scoreboard_scoring_enabled: false });

    expect(fixture.nativeElement.querySelector('.buttons')).toBeNull();
    expect(fixture.nativeElement.querySelector('.end-match-button')).toBeNull();
  });

  it('shows +1/-1 and end-match controls once scoreboard_scoring_enabled is true', () => {
    const fixture = setup(scoringMatchState);

    expect(fixture.nativeElement.querySelectorAll('.buttons').length).toBe(2);
    expect(fixture.nativeElement.querySelector('.end-match-button')).not.toBeNull();
  });

  it('clicking +1 on team A calls CourtControlService.score with side A', () => {
    const scoreSpy = vi.fn().mockReturnValue(
      of({ applied: true, match_id: 'm1', status: 'in_progress', score_a: 2, score_b: 2, winner_team: null }),
    );
    const fixture = setup(scoringMatchState, true, { score: scoreSpy });

    const teamAButtons = fixture.nativeElement.querySelector('.buttons--a');
    const plusOne: HTMLButtonElement = teamAButtons.querySelector('button');
    plusOne.click();

    expect(scoreSpy).toHaveBeenCalledWith('tok', 'm1', 'A', 1);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.team--a .score').textContent).toContain('2');
  });

  it('pulses team A\'s score after a successful local +1, not team B\'s', async () => {
    const scoreSpy = vi.fn().mockReturnValue(
      of({ applied: true, match_id: 'm1', status: 'in_progress', score_a: 2, score_b: 1, winner_team: null }),
    );
    const fixture = setup(scoringMatchState, true, { score: scoreSpy });

    fixture.nativeElement.querySelector('.buttons--a button').click();
    // triggerScorePulse defers setting the pulse signal to the next
    // animation frame (see ScoreboardComponent) so the CSS animation
    // actually restarts — give that a real tick before asserting.
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.team--a .score').classList).toContain('score--pulse');
    expect(fixture.nativeElement.querySelector('.team--b .score').classList).not.toContain('score--pulse');
  });

  it('confirming the end-match dialog calls CourtControlService.endMatch', () => {
    const endMatchSpy = vi.fn().mockReturnValue(
      of({ applied: true, match_id: 'm1', status: 'abandoned', score_a: 1, score_b: 2, winner_team: null }),
    );
    const fixture = setup(scoringMatchState, true, { endMatch: endMatchSpy });
    const component = fixture.componentInstance;

    component.confirmEndMatch();

    expect(endMatchSpy).toHaveBeenCalledWith('tok', 'm1');
  });

  // 024-add-english-language FR-003d (2026-09-15 修正): the scoreboard has
  // no login and so no language switcher of its own — unlike the
  // control-panel routes, it MUST NOT render one, and MUST instead apply
  // whichever language the court response's `owner_language` carries.
  it('does not show a language switcher, even before a court ever loads', () => {
    const fixture = setup(null, true, {}, { watchCourtLink: () => NEVER });

    expect(fixture.nativeElement.querySelector('app-language-switcher')).toBeNull();
  });

  it('applies owner_language once the court loads successfully', () => {
    setup(scoringMatchState);

    expect(TestBed.inject(TranslateService).currentLang()).toBe('en');
  });

  it('does not apply a language while still loading (no court response yet)', () => {
    setup(null, true, {}, { watchCourtLink: () => NEVER });

    expect(TestBed.inject(TranslateService).currentLang()).not.toBe('en');
  });

  // 029-serve-rotation-display

  it('merges serve from a match.scoreUpdated event without refetching (US1 FR-009)', () => {
    const scoreUpdated$ = new Subject<{ data: unknown }>();
    const fixture = setup(
      {
        court_id: 'c1',
        round_number: 1,
        current_match: {
          match_id: 'm1',
          status: 'in_progress',
          score_a: 0,
          score_b: 0,
          participants: [
            { roster_entry_id: 'p1', nickname: '陳甲', team: 'A' },
            { roster_entry_id: 'p2', nickname: '劉乙', team: 'A' },
            { roster_entry_id: 'p3', nickname: '徐丙', team: 'B' },
            { roster_entry_id: 'p4', nickname: '李丁', team: 'B' },
          ],
          serve: doublesServe,
        },
        waiting_reason: null,
        next_up: null,
      },
      true,
      {},
      undefined,
      realtimeStubWithEvent('match.scoreUpdated', scoreUpdated$),
    );

    // Side-out: B (徐丙) takes over serve.
    scoreUpdated$.next({
      data: {
        match_id: 'm1',
        score_a: 5,
        score_b: 8,
        serve: {
          server_roster_entry_id: 'p3',
          server_team: 'B',
          team_a_right_roster_entry_id: 'p1',
          team_a_left_roster_entry_id: 'p2',
          team_b_right_roster_entry_id: 'p3',
          team_b_left_roster_entry_id: 'p4',
        },
      },
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.team--a .score').textContent).toContain('5');
    expect(fixture.nativeElement.querySelector('.station--server').textContent).toContain('徐丙');
  });

  it('pulses only the side whose score actually changed in a match.scoreUpdated event', async () => {
    const scoreUpdated$ = new Subject<{ data: unknown }>();
    const fixture = setup(
      {
        court_id: 'c1',
        round_number: 1,
        current_match: {
          match_id: 'm1',
          status: 'in_progress',
          score_a: 5,
          score_b: 8,
          participants: [
            { roster_entry_id: 'p1', nickname: '陳甲', team: 'A' },
            { roster_entry_id: 'p2', nickname: '徐丙', team: 'B' },
          ],
        },
        waiting_reason: null,
        next_up: null,
      },
      true,
      {},
      undefined,
      realtimeStubWithEvent('match.scoreUpdated', scoreUpdated$),
    );

    // Only B's score actually changes (8 -> 9); A stays at 5.
    scoreUpdated$.next({
      data: { match_id: 'm1', score_a: 5, score_b: 9, serve: null },
    });
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.team--b .score').classList).toContain('score--pulse');
    expect(fixture.nativeElement.querySelector('.team--a .score').classList).not.toContain('score--pulse');
  });

  it('reflects a reconnect-triggered full state refetch (US3 FR-011, spec Edge Case)', () => {
    const reconnect$ = new Subject<void>();
    const buildState = (servingNickname: 'A' | 'B') => ({
      court_id: 'c1',
      round_number: 1,
      current_match: {
        match_id: 'm1',
        status: 'in_progress',
        score_a: 5,
        score_b: 8,
        participants: [
          { roster_entry_id: 'p1', nickname: '陳甲', team: 'A' },
          { roster_entry_id: 'p2', nickname: '劉乙', team: 'A' },
          { roster_entry_id: 'p3', nickname: '徐丙', team: 'B' },
          { roster_entry_id: 'p4', nickname: '李丁', team: 'B' },
        ],
        serve: {
          server_roster_entry_id: servingNickname === 'A' ? 'p1' : 'p3',
          server_team: servingNickname,
          team_a_right_roster_entry_id: 'p1',
          team_a_left_roster_entry_id: 'p2',
          team_b_right_roster_entry_id: 'p3',
          team_b_left_roster_entry_id: 'p4',
        },
      },
      waiting_reason: null,
      next_up: null,
    });
    const getStateSpy = vi
      .fn()
      .mockReturnValueOnce(of(buildState('A')))
      .mockReturnValueOnce(of(buildState('B')));

    const fixture = setup(
      null,
      true,
      { getState: getStateSpy },
      undefined,
      undefined,
      reconnectStubWithTrigger(reconnect$),
    );
    expect(fixture.nativeElement.querySelector('.station--server').textContent).toContain('陳甲');

    reconnect$.next();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.station--server').textContent).toContain('徐丙');
  });
});
