import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { signal } from '@angular/core';
import { of, EMPTY, NEVER, throwError } from 'rxjs';
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

/** 038: the same court with the match in detailed-scoring mode. */
const detailedCourt: CourtScheduleStatus = {
  ...court,
  current_match: { ...court.current_match!, detailed_scoring_enabled: true },
};

/** 039: a simple-mode court at an arbitrary score, played to 21 / cap 30. */
function courtAt(scoreA: number, scoreB: number, detailed = false): CourtScheduleStatus {
  return {
    ...court,
    current_match: {
      ...court.current_match!,
      score_a: scoreA,
      score_b: scoreB,
      detailed_scoring_enabled: detailed,
      target_score: 21,
      cap_score: 30,
    },
  };
}

/** A `scoreMatch` result for a point that keeps the match going. */
function pointApplied(overrides: Record<string, unknown> = {}) {
  return {
    applied: true,
    match_id: 'm1',
    status: 'in_progress',
    score_a: 6,
    score_b: 7,
    winner_team: null,
    score_event_id: 'ev1',
    serve: doublesServe,
    ...overrides,
  };
}

function setup(
  overrideCourt: CourtScheduleStatus = court,
  services: Record<string, unknown> = {},
) {
  TestBed.configureTestingModule({
    imports: [CourtControlComponent],
    providers: [
      provideTranslateService({}),
      { provide: RealtimeService, useFactory: realtimeStub },
      { provide: ReconnectRefetchService, useFactory: reconnectStub },
      {
        provide: ScheduleService,
        useValue: {
          scoreMatch: () => of(pointApplied()),
          endMatch: () => of({}),
          recordShotPlacement: () => of({ recorded: true }),
          undoMatchCompletion: () => of(pointApplied()),
          ...services,
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(CourtControlComponent);
  fixture.componentRef.setInput('groupId', 'g1');
  fixture.componentRef.setInput('court', overrideCourt);
  fixture.detectChanges();
  return fixture;
}

/** The "+1" buttons, left block then right block. */
function plusButtons(fixture: ReturnType<typeof setup>): HTMLButtonElement[] {
  return Array.from(
    fixture.nativeElement.querySelectorAll('.scoring-controls .buttons'),
  ).map((group) => (group as HTMLElement).querySelector('button') as HTMLButtonElement);
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

/** 038-admin-detailed-scoring: the admin board gains the same score-then-record
 * flow the public control panel has had since 032. */
describe('CourtControlComponent detailed scoring', () => {
  // The picker component is always instantiated inside the match block (same
  // as the public control panel and the scoreboard) — it's `open()` that
  // gates it, so "no dialog" is asserted on the call, not on the DOM.
  it('simple mode is untouched: "+1" scores directly and never opens the picker', () => {
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(court, { scoreMatch: scoreSpy });
    const openSpy = vi.spyOn(fixture.componentInstance.shotPlacementPicker()!, 'open');

    plusButtons(fixture)[0].click();

    expect(scoreSpy).toHaveBeenCalledWith('g1', 'c1', 'm1', 'A', 1);
    expect(openSpy).not.toHaveBeenCalled();
  });

  it('displayCourt() passes the live input straight through while nothing is frozen', () => {
    const fixture = setup();

    expect(fixture.componentInstance.displayCourt()).toBe(court);
  });

  it('detailed mode: "+1" scores AND opens the picker in the same tap (FR-002, FR-003)', () => {
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(detailedCourt, { scoreMatch: scoreSpy });
    const openSpy = vi.spyOn(fixture.componentInstance.shotPlacementPicker()!, 'open');

    plusButtons(fixture)[0].click();

    expect(scoreSpy).toHaveBeenCalledWith('g1', 'c1', 'm1', 'A', 1);
    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(fixture.componentInstance.pendingScoringSide()).toBe('A');
  });

  it('captures the serve state from BEFORE the point, not the post-point value (FR-004)', () => {
    const fixture = setup(detailedCourt);

    plusButtons(fixture)[0].click();

    // doublesServe has team A serving with score_a 5 — both read pre-point.
    expect(fixture.componentInstance.pendingServingTeam()).toBe('A');
    expect(fixture.componentInstance.pendingServingScore()).toBe(5);
    expect(fixture.componentInstance.pendingServingRosterEntryId()).toBe('p1');
  });

  it('confirm forwards every detail field, with the score_event_id from the +1 (FR-004)', () => {
    const recordSpy = vi.fn().mockReturnValue(of({ recorded: true }));
    const fixture = setup(detailedCourt, { recordShotPlacement: recordSpy });

    plusButtons(fixture)[0].click();
    fixture.componentInstance.onShotPlacementConfirmed({
      rosterEntryId: 'p1',
      losingRosterEntryId: 'p3',
      landingX: 0.62,
      landingY: 0.18,
      endingType: 'smash' as never,
    });

    expect(recordSpy).toHaveBeenCalledWith(
      'g1', 'c1', 'm1', 'ev1', 'p1', 'p3', 0.62, 0.18, 'smash',
    );
  });

  it('closes the picker when the +1 was not applied after all (FR-017)', () => {
    const fixture = setup(detailedCourt, {
      scoreMatch: () => of(pointApplied({ applied: false, score_event_id: null })),
    });
    const skipSpy = vi.spyOn(fixture.componentInstance.shotPlacementPicker()!, 'skip');

    plusButtons(fixture)[0].click();

    expect(skipSpy).toHaveBeenCalledTimes(1);
    expect(fixture.componentInstance.displayCourt()).toBe(detailedCourt);
  });

  it('skip keeps the point and records nothing (FR-006)', () => {
    const recordSpy = vi.fn().mockReturnValue(of({ recorded: true }));
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(detailedCourt, { scoreMatch: scoreSpy, recordShotPlacement: recordSpy });

    plusButtons(fixture)[0].click();
    fixture.componentInstance.onShotPlacementClosed(); // what skip() ends up firing

    expect(scoreSpy).toHaveBeenCalledTimes(1); // the point stands
    expect(recordSpy).not.toHaveBeenCalled();
    expect(fixture.componentInstance.displayCourt()).toBe(detailedCourt); // freeze lifted
  });

  it('cancel on a continuing match sends the matching -1 (FR-007)', () => {
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const undoSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(detailedCourt, { scoreMatch: scoreSpy, undoMatchCompletion: undoSpy });

    plusButtons(fixture)[0].click();
    fixture.componentInstance.onShotPlacementCancelled();

    expect(scoreSpy).toHaveBeenNthCalledWith(2, 'g1', 'c1', 'm1', 'A', -1);
    expect(undoSpy).not.toHaveBeenCalled();
  });

  it('cancel on a match-ending point undoes the completion instead of a -1 (FR-008)', () => {
    const scoreSpy = vi.fn().mockReturnValue(
      of(pointApplied({ status: 'completed', winner_team: 'A' })),
    );
    const undoSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(detailedCourt, { scoreMatch: scoreSpy, undoMatchCompletion: undoSpy });

    plusButtons(fixture)[0].click();
    fixture.componentInstance.onShotPlacementCancelled();

    expect(undoSpy).toHaveBeenCalledWith('g1', 'c1', 'm1', 'A');
    expect(scoreSpy).toHaveBeenCalledTimes(1); // no -1 was sent
  });

  it('surfaces a readable reason when the cancel is refused (FR-009)', () => {
    const fixture = setup(detailedCourt, {
      scoreMatch: () => of(pointApplied({ status: 'completed', winner_team: 'A' })),
      undoMatchCompletion: () =>
        throwError(() => ({
          errorCode: 'ROUND_ALREADY_ADVANCED',
          i18nKey: 'errors.ROUND_ALREADY_ADVANCED',
          detail: null,
          status: 409,
        })),
    });

    plusButtons(fixture)[0].click();
    fixture.componentInstance.onShotPlacementCancelled();

    expect(fixture.componentInstance.cancelScoreErrorKey()).toBe('errors.ROUND_ALREADY_ADVANCED');
  });

  it('holds the frozen court when a match-ending refetch blanks current_match (FR-011)', () => {
    const fixture = setup(detailedCourt, {
      scoreMatch: () => of(pointApplied({ status: 'completed', winner_team: 'A', score_a: 21 })),
    });

    plusButtons(fixture)[0].click();
    // The parent refetches on match.ended and the court comes back empty.
    fixture.componentRef.setInput('court', { ...detailedCourt, current_match: null });
    fixture.detectChanges();

    expect(fixture.componentInstance.displayCourt().current_match).not.toBeNull();
    expect(fixture.nativeElement.querySelector('app-shot-placement-picker')).toBeTruthy();
  });

  it('shows the just-scored point behind the open picker (FR-012)', () => {
    const fixture = setup(detailedCourt, {
      scoreMatch: () => of(pointApplied({ score_a: 6 })),
    });

    plusButtons(fixture)[0].click();

    expect(fixture.componentInstance.displayCourt().current_match!.score_a).toBe(6);
  });

  it('lifts the freeze once the picker closes, snapping to the newest input (FR-011)', () => {
    const fixture = setup(detailedCourt, {
      scoreMatch: () => of(pointApplied({ status: 'completed', winner_team: 'A' })),
    });

    plusButtons(fixture)[0].click();
    const afterMatch = { ...detailedCourt, current_match: null };
    fixture.componentRef.setInput('court', afterMatch);
    fixture.detectChanges();
    fixture.componentInstance.onShotPlacementClosed();

    expect(fixture.componentInstance.displayCourt()).toBe(afterMatch);
  });

  it('double-tapping "+1" scores once and opens one picker (FR-013)', () => {
    const scoreSpy = vi.fn().mockReturnValue(NEVER); // in flight, never resolves
    const fixture = setup(detailedCourt, { scoreMatch: scoreSpy });
    const openSpy = vi.spyOn(fixture.componentInstance.shotPlacementPicker()!, 'open');

    plusButtons(fixture)[0].click();
    plusButtons(fixture)[0].click();

    expect(scoreSpy).toHaveBeenCalledTimes(1);
    expect(openSpy).toHaveBeenCalledTimes(1);
  });

  it('double-tapping "+1" in simple mode also scores only once (FR-013)', () => {
    const scoreSpy = vi.fn().mockReturnValue(NEVER);
    const fixture = setup(court, { scoreMatch: scoreSpy });

    plusButtons(fixture)[0].click();
    plusButtons(fixture)[0].click();

    expect(scoreSpy).toHaveBeenCalledTimes(1);
  });
});

/** 039-match-point-confirm: simple mode has no way back from the point that
 * ends a match — once the match completes the backend refuses every score
 * delta, so even "-1" silently does nothing — so it gets asked first. */
describe('CourtControlComponent match-point confirmation', () => {
  function dialogOpenSpy(fixture: ReturnType<typeof setup>) {
    return vi.spyOn(fixture.componentInstance.matchPointDialog()!, 'open');
  }

  it('asks before the point that would end the match (FR-001)', () => {
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(courtAt(20, 15), { scoreMatch: scoreSpy });
    const openSpy = dialogOpenSpy(fixture);

    plusButtons(fixture)[0].click();

    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(scoreSpy).not.toHaveBeenCalled(); // nothing sent before confirming
    expect(fixture.componentInstance.pendingMatchPointSide()).toBe('A');
  });

  it('scores only once the scorer confirms (FR-003)', () => {
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(courtAt(20, 15), { scoreMatch: scoreSpy });

    plusButtons(fixture)[0].click();
    fixture.componentInstance.onMatchPointConfirmed();

    expect(scoreSpy).toHaveBeenCalledWith('g1', 'c1', 'm1', 'A', 1);
  });

  it('cancelling sends nothing and leaves the board ready to score (FR-004)', () => {
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(courtAt(20, 15), { scoreMatch: scoreSpy });
    const openSpy = dialogOpenSpy(fixture);

    plusButtons(fixture)[0].click();
    fixture.componentInstance.onMatchPointDialogClosed(); // cancel button, or Esc

    expect(scoreSpy).not.toHaveBeenCalled();
    expect(fixture.componentInstance.pendingMatchPointSide()).toBeNull();

    plusButtons(fixture)[0].click(); // and the next press still works
    expect(openSpy).toHaveBeenCalledTimes(2);
  });

  it('DEUCE: 20-20 does not ask — 21-20 leads by one, nobody has won (FR-009)', () => {
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(courtAt(20, 20), { scoreMatch: scoreSpy });
    const openSpy = dialogOpenSpy(fixture);

    plusButtons(fixture)[0].click();

    expect(openSpy).not.toHaveBeenCalled();
    expect(scoreSpy).toHaveBeenCalledWith('g1', 'c1', 'm1', 'A', 1);
  });

  it('CAP: 29-29 asks on BOTH sides — reaching 30 wins outright (FR-009, FR-010)', () => {
    const fixture = setup(courtAt(29, 29));
    const openSpy = dialogOpenSpy(fixture);

    plusButtons(fixture)[0].click();
    expect(openSpy).toHaveBeenCalledTimes(1);
    fixture.componentInstance.onMatchPointDialogClosed();

    plusButtons(fixture)[1].click();
    expect(openSpy).toHaveBeenCalledTimes(2);
    expect(fixture.componentInstance.pendingMatchPointSide()).toBe('B');
  });

  it('an ordinary point is untouched (FR-007)', () => {
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(courtAt(19, 15), { scoreMatch: scoreSpy });
    const openSpy = dialogOpenSpy(fixture);

    plusButtons(fixture)[0].click();

    expect(openSpy).not.toHaveBeenCalled();
    expect(scoreSpy).toHaveBeenCalledWith('g1', 'c1', 'm1', 'A', 1);
  });

  it('"-1" never asks, even at match point (FR-006)', () => {
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(courtAt(20, 15), { scoreMatch: scoreSpy });
    const openSpy = dialogOpenSpy(fixture);

    const minusButtons: HTMLButtonElement[] = Array.from(
      fixture.nativeElement.querySelectorAll('.scoring-controls .buttons'),
    ).map((g) => (g as HTMLElement).querySelectorAll('button')[1] as HTMLButtonElement);
    minusButtons[0].click();

    expect(openSpy).not.toHaveBeenCalled();
    expect(scoreSpy).toHaveBeenCalledWith('g1', 'c1', 'm1', 'A', -1);
  });

  it('detailed mode keeps its own picker and adds no second prompt (FR-005)', () => {
    const fixture = setup(courtAt(20, 15, true));
    const openSpy = dialogOpenSpy(fixture);
    const pickerSpy = vi.spyOn(fixture.componentInstance.shotPlacementPicker()!, 'open');

    plusButtons(fixture)[0].click();

    expect(pickerSpy).toHaveBeenCalledTimes(1);
    expect(openSpy).not.toHaveBeenCalled();
  });

  it('double-tapping at match point opens one dialog and scores once (FR-014)', () => {
    // jsdom has no modal behaviour, so the real browser's "the backdrop
    // swallows the second tap" cannot be relied on here — or verified at
    // all. plusPressed's re-entrancy guard is what makes this hold.
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const fixture = setup(courtAt(20, 15), { scoreMatch: scoreSpy });
    const openSpy = dialogOpenSpy(fixture);

    plusButtons(fixture)[0].click();
    plusButtons(fixture)[0].click();

    expect(openSpy).toHaveBeenCalledTimes(1);

    fixture.componentInstance.onMatchPointConfirmed();
    expect(scoreSpy).toHaveBeenCalledTimes(1);
  });

  it('confirming after the connection drops sends nothing (FR-012)', () => {
    // The "+" button is already disabled offline, but the dialog can be open
    // when the connection goes — that window is what this covers.
    const scoreSpy = vi.fn().mockReturnValue(of(pointApplied()));
    const connectionState = signal('connected');
    TestBed.configureTestingModule({
      imports: [CourtControlComponent],
      providers: [
        provideTranslateService({}),
        { provide: RealtimeService, useValue: { connectionState, subscribe: () => EMPTY } },
        { provide: ReconnectRefetchService, useFactory: reconnectStub },
        {
          provide: ScheduleService,
          useValue: { scoreMatch: scoreSpy, endMatch: () => of({}) },
        },
      ],
    });
    const fixture = TestBed.createComponent(CourtControlComponent);
    fixture.componentRef.setInput('groupId', 'g1');
    fixture.componentRef.setInput('court', courtAt(20, 15));
    fixture.detectChanges();

    fixture.componentInstance.plusPressed('A');
    connectionState.set('disconnected');
    fixture.componentInstance.onMatchPointConfirmed();

    expect(scoreSpy).not.toHaveBeenCalled();
  });

  it('accepts the server verdict when the confirmed point did not end it (FR-013)', () => {
    // The client only decides whether to ASK; the server decides whether the
    // match is over. Here it comes back still in progress.
    const scoreSpy = vi
      .fn()
      .mockReturnValue(of(pointApplied({ status: 'in_progress', winner_team: null })));
    const changed = vi.fn();
    const fixture = setup(courtAt(20, 15), { scoreMatch: scoreSpy });
    fixture.componentInstance.changed.subscribe(changed);

    plusButtons(fixture)[0].click();
    fixture.componentInstance.onMatchPointConfirmed();

    expect(scoreSpy).toHaveBeenCalledTimes(1);
    expect(changed).toHaveBeenCalled(); // refetch, rather than assuming an end
  });
});
