import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import {
  ENDING_TYPES,
  EndingType,
  ParticipantSummary,
  Team,
} from '../../core/api/court-live-state.models';
import { ShotPlacementPickerComponent } from './shot-placement-picker.component';

const participants: ParticipantSummary[] = [
  { roster_entry_id: 'p1', nickname: '陳甲', team: 'A' },
  { roster_entry_id: 'p2', nickname: '劉乙', team: 'A' },
  { roster_entry_id: 'p3', nickname: '徐丙', team: 'B' },
  { roster_entry_id: 'p4', nickname: '李丁', team: 'B' },
];

const singlesParticipants: ParticipantSummary[] = [
  { roster_entry_id: 'p1', nickname: '陳甲', team: 'A' },
  { roster_entry_id: 'p3', nickname: '徐丙', team: 'B' },
];

const POINTER_ID = 1;

function pointerEvent(type: string, clientX: number, clientY: number): PointerEvent {
  // bubbles: true — the handlers live on .court-area, and .court (what
  // tests measure the mocked rect against) is nested inside it, same as a
  // real tap anywhere in that area would bubble up.
  return new PointerEvent(type, { bubbles: true, clientX, clientY, pointerId: POINTER_ID });
}

function pointerDown(target: Element, clientX: number, clientY: number): void {
  target.dispatchEvent(pointerEvent('pointerdown', clientX, clientY));
}

function pointerMove(target: Element, clientX: number, clientY: number): void {
  target.dispatchEvent(pointerEvent('pointermove', clientX, clientY));
}

function pointerUp(target: Element, clientX: number, clientY: number): void {
  target.dispatchEvent(pointerEvent('pointerup', clientX, clientY));
}

/** A quick tap: down then immediately up, never reaching the long-press
 * threshold — this is the "plain click" replacement used by most tests
 * below, since the interaction is pointer-based now (needed to raise the
 * magnifier on a hold, see component.ts). */
function tap(target: Element, clientX: number, clientY: number): void {
  pointerDown(target, clientX, clientY);
  pointerUp(target, clientX, clientY);
}

/** 032-score-then-record: `scoringTeam` defaults to 'A' — the caller (a
 * wiring component) always sets it before open() to whichever side's "+"
 * was just pressed and already scored. */
function setup(
  participantsList: ParticipantSummary[] = participants,
  scoringTeam: Team = 'A',
  servingTeam: Team | null = null,
) {
  TestBed.configureTestingModule({
    imports: [ShotPlacementPickerComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(ShotPlacementPickerComponent);
  fixture.componentRef.setInput('participants', participantsList);
  fixture.componentRef.setInput('scoringTeam', scoringTeam);
  fixture.componentRef.setInput('servingTeam', servingTeam);
  fixture.detectChanges();
  const courtAreaEl: HTMLDivElement = fixture.nativeElement.querySelector('.court-area');
  const courtEl: HTMLDivElement = fixture.nativeElement.querySelector('.court');
  // jsdom doesn't implement pointer capture — no-op it rather than throw,
  // same spirit as the <dialog> guards in the component itself.
  courtAreaEl.setPointerCapture = vi.fn();
  // jsdom always reports a zero-size rect — stub .court's (not .court-area's
  // — the pointer handlers measure against the inner rectangle, see the
  // component's doc comment) to a known 200x100 box so a synthetic
  // pointer event's clientX/clientY maps to a predictable fraction,
  // including outside [0, 1] for a tap in .court-area's margin around this
  // box. Center x (clientX=150) sits exactly on the net (x=0.5): below it
  // is team A's half, above it team B's (data-model.md Decision 1).
  vi.spyOn(courtEl, 'getBoundingClientRect').mockReturnValue({
    left: 50,
    top: 25,
    width: 200,
    height: 100,
    right: 250,
    bottom: 125,
    x: 50,
    y: 25,
    toJSON: () => '',
  });
  return { fixture, courtAreaEl, courtEl };
}

/** .players-section renders the scoring pool then the losing pool as two
 * separate `.players` button groups, in that order (component.html). */
function scoringButtons(fixture: { nativeElement: HTMLElement }): NodeListOf<HTMLButtonElement> {
  return fixture.nativeElement.querySelectorAll<HTMLButtonElement>('.players')[0].querySelectorAll('.player');
}
function losingButtons(fixture: { nativeElement: HTMLElement }): NodeListOf<HTMLButtonElement> {
  return fixture.nativeElement.querySelectorAll<HTMLButtonElement>('.players')[1].querySelectorAll('.player');
}
function nicknames(buttons: NodeListOf<HTMLButtonElement>): string[] {
  return Array.from(buttons).map((b) => b.textContent?.trim() ?? '');
}

describe('ShotPlacementPickerComponent', () => {
  it('renders only the credited team in the scoring section and the other team in the losing section', () => {
    const { fixture } = setup(participants, 'A');

    expect(nicknames(scoringButtons(fixture))).toEqual(['陳甲', '劉乙']); // team A (credited)
    expect(nicknames(losingButtons(fixture))).toEqual(['徐丙', '李丁']); // team B
  });

  it('swaps which team is offered in each section when the other team was credited', () => {
    const { fixture } = setup(participants, 'B');

    expect(nicknames(scoringButtons(fixture))).toEqual(['徐丙', '李丁']); // team B (credited)
    expect(nicknames(losingButtons(fixture))).toEqual(['陳甲', '劉乙']); // team A
  });

  it('allows confirming with nothing selected at all (032-optional-shot-placement-detail)', () => {
    const { fixture } = setup(participants, 'A');
    const confirmButton = (): HTMLButtonElement =>
      fixture.nativeElement.querySelector('.actions button:last-of-type');

    expect(confirmButton().disabled).toBe(false);
  });

  it('allows confirming with only some fields chosen', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A');
    const confirmButton = (): HTMLButtonElement =>
      fixture.nativeElement.querySelector('.actions button:last-of-type');

    // .court's mocked rect is left:50/top:25/width:200/height:100 -> (200, 75)
    // is x=0.75 (B's half) -> consistent with team A already credited.
    tap(courtAreaEl, 200, 75);
    fixture.detectChanges();
    expect(confirmButton().disabled).toBe(false);

    scoringButtons(fixture)[0].click(); // p1
    fixture.detectChanges();
    expect(confirmButton().disabled).toBe(false);
  });

  it('disables confirm once the landing contradicts the credited side', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A');
    const confirmButton = (): HTMLButtonElement =>
      fixture.nativeElement.querySelector('.actions button:last-of-type');

    // (100, 75) -> x=0.25 (A's own half) — contradicts A already scoring.
    tap(courtAreaEl, 100, 75);
    fixture.detectChanges();

    expect(confirmButton().disabled).toBe(true);
  });

  it('re-tapping the court area before confirming replaces the pending point, not adds to it', () => {
    const { fixture, courtAreaEl } = setup();

    tap(courtAreaEl, 150, 75);
    fixture.detectChanges();
    tap(courtAreaEl, 90, 105);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('.landing-marker').length).toBe(1);
  });

  it('marks a landing outside the drawn court as an out-of-bounds point (FR-010)', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A');
    const confirmedSpy = vi.fn();
    fixture.componentInstance.confirmed.subscribe(confirmedSpy);
    // .court's mocked rect is left:50/top:25/width:200/height:100 (setup())
    // — tapping at (20, 10) lands well outside that box on both axes, which
    // never conflicts with whichever side was already credited.
    tap(courtAreaEl, 20, 10);
    fixture.detectChanges();
    scoringButtons(fixture)[0].click(); // p1
    fixture.detectChanges();
    losingButtons(fixture)[0].click(); // p3
    fixture.detectChanges();
    fixture.nativeElement.querySelector('.actions button:last-of-type').click();

    expect(confirmedSpy).toHaveBeenCalledTimes(1);
    const { landingX, landingY, rosterEntryId, losingRosterEntryId } = confirmedSpy.mock.calls[0][0];
    expect(landingX).toBeLessThan(0);
    expect(landingY).toBeLessThan(0);
    // Still within the server's accepted range (data-model.md), not an
    // arbitrarily large value from an even farther-out tap.
    expect(landingX).toBeGreaterThanOrEqual(-0.3);
    expect(landingY).toBeGreaterThanOrEqual(-0.3);
    expect(rosterEntryId).toBe('p1');
    expect(losingRosterEntryId).toBe('p3');
  });

  it('re-selecting a player before confirming replaces the pending choice', () => {
    const { fixture } = setup(participants, 'A');

    scoringButtons(fixture)[0].click(); // p1
    fixture.detectChanges();
    scoringButtons(fixture)[1].click(); // p2
    fixture.detectChanges();

    const selected = fixture.nativeElement.querySelectorAll('.player--selected');
    expect(selected.length).toBe(1);
    expect(selected[0].textContent?.trim()).toBe('劉乙');
  });

  it('emits the final point/scoring player/losing player only once, on confirm', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A');
    const confirmedSpy = vi.fn();
    fixture.componentInstance.confirmed.subscribe(confirmedSpy);

    // .court's mocked rect is left:50/top:25/width:200/height:100 — (200, 75)
    // is x=0.75 (B's half), consistent with team A already credited.
    tap(courtAreaEl, 200, 75);
    fixture.detectChanges();
    scoringButtons(fixture)[0].click(); // p1
    fixture.detectChanges();
    losingButtons(fixture)[0].click(); // p3
    fixture.detectChanges();
    expect(confirmedSpy).not.toHaveBeenCalled();

    fixture.nativeElement.querySelector('.actions button:last-of-type').click();

    expect(confirmedSpy).toHaveBeenCalledTimes(1);
    expect(confirmedSpy).toHaveBeenCalledWith({
      rosterEntryId: 'p1',
      losingRosterEntryId: 'p3',
      landingX: 0.75,
      landingY: 0.5,
      endingType: null,
    });
  });

  // --- 032-skip-and-cancel-score: the three distinct actions ---------------

  it('confirm() sends null for any field the scorer never picked', () => {
    const { fixture } = setup(participants, 'A');
    const confirmedSpy = vi.fn();
    fixture.componentInstance.confirmed.subscribe(confirmedSpy);

    fixture.nativeElement.querySelector('.actions button:last-of-type').click();

    expect(confirmedSpy).toHaveBeenCalledTimes(1);
    expect(confirmedSpy).toHaveBeenCalledWith({
      rosterEntryId: null,
      losingRosterEntryId: null,
      landingX: null,
      landingY: null,
      endingType: null,
    });
  });

  it('skip() closes without recording anything, even if fields were selected', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A');
    const confirmedSpy = vi.fn();
    fixture.componentInstance.confirmed.subscribe(confirmedSpy);

    tap(courtAreaEl, 200, 75);
    fixture.detectChanges();
    scoringButtons(fixture)[0].click();
    fixture.detectChanges();

    fixture.nativeElement.querySelector('.actions button:first-of-type').click();

    expect(confirmedSpy).not.toHaveBeenCalled();
  });

  it('cancelScore() emits scoreCancelled and never emits confirmed', () => {
    const { fixture } = setup(participants, 'A');
    const confirmedSpy = vi.fn();
    const cancelledSpy = vi.fn();
    fixture.componentInstance.confirmed.subscribe(confirmedSpy);
    fixture.componentInstance.scoreCancelled.subscribe(cancelledSpy);

    const buttons = fixture.nativeElement.querySelectorAll('.actions button');
    (buttons[1] as HTMLButtonElement).click(); // Cancel Score is the 2nd action button

    expect(cancelledSpy).toHaveBeenCalledTimes(1);
    expect(confirmedSpy).not.toHaveBeenCalled();
  });

  it('cancelScore() is still available even when the landing conflicts', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A');
    const cancelledSpy = vi.fn();
    fixture.componentInstance.scoreCancelled.subscribe(cancelledSpy);

    tap(courtAreaEl, 100, 75); // A's own half -> conflict, confirm disabled
    fixture.detectChanges();

    const buttons = fixture.nativeElement.querySelectorAll('.actions button');
    (buttons[1] as HTMLButtonElement).click();

    expect(cancelledSpy).toHaveBeenCalledTimes(1);
  });

  it('emits closed when skip() is clicked (032-freeze-while-picker-open)', () => {
    const { fixture } = setup(participants, 'A');
    const closedSpy = vi.fn();
    fixture.componentInstance.closed.subscribe(closedSpy);

    fixture.nativeElement.querySelectorAll('.actions button')[0].click();

    expect(closedSpy).toHaveBeenCalledTimes(1);
  });

  it('emits closed when cancelScore() is clicked', () => {
    const { fixture } = setup(participants, 'A');
    const closedSpy = vi.fn();
    fixture.componentInstance.closed.subscribe(closedSpy);

    fixture.nativeElement.querySelectorAll('.actions button')[1].click();

    expect(closedSpy).toHaveBeenCalledTimes(1);
  });

  it('emits closed when confirm() is clicked', () => {
    const { fixture } = setup(participants, 'A');
    const closedSpy = vi.fn();
    fixture.componentInstance.closed.subscribe(closedSpy);

    fixture.nativeElement.querySelectorAll('.actions button')[2].click();

    expect(closedSpy).toHaveBeenCalledTimes(1);
  });

  // --- 032-score-then-record: landing consistency with the credited side --

  it('empties both pools when an in-bounds landing falls on the credited side\'s own half', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A');

    // (100, 75) -> x=0.25 (A's own half) — contradicts A already scoring.
    tap(courtAreaEl, 100, 75);
    fixture.detectChanges();

    expect(nicknames(scoringButtons(fixture))).toEqual([]);
    expect(nicknames(losingButtons(fixture))).toEqual([]);
    expect(fixture.nativeElement.querySelector('.hint--warning')).not.toBeNull();
  });

  // --- 032-serve-fault-landing: a serve fault favors the credited side too

  it('does not conflict for a short-serve-fault landing on the credited side\'s own half', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A');

    // (140, 75) -> x=0.45: between the net (0.5) and A's short service line
    // (~0.3522) — the serve never crossed it, so A (the receiver) wins the
    // point on a service fault, not because A itself failed to return it.
    tap(courtAreaEl, 140, 75);
    fixture.detectChanges();

    expect(nicknames(scoringButtons(fixture))).toEqual(['陳甲', '劉乙']);
    expect(nicknames(losingButtons(fixture))).toEqual(['徐丙', '李丁']);
    expect(fixture.nativeElement.querySelector('.hint--warning')).toBeNull();
    expect(fixture.nativeElement.querySelector('.status-badge')).not.toBeNull();
  });

  it('does not conflict for a long-serve-fault landing on the credited side\'s own half in doubles', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A'); // doubles fixture

    // (56, 75) -> x=0.03: past A's long service line (~0.0567, doubles
    // only) but short of A's own baseline — a doubles serve there never
    // reached the legal box, a service fault favoring A.
    tap(courtAreaEl, 56, 75);
    fixture.detectChanges();

    expect(nicknames(scoringButtons(fixture))).toEqual(['陳甲', '劉乙']);
    expect(nicknames(losingButtons(fixture))).toEqual(['徐丙', '李丁']);
    expect(fixture.nativeElement.querySelector('.hint--warning')).toBeNull();
    expect(fixture.nativeElement.querySelector('.status-badge')).not.toBeNull();
  });

  it('conflicts (not a fault) for a short-serve-fault-zone landing when the credited side was itself serving', () => {
    // A won this rally while already serving (no side-out) — a landing on
    // A's own half here can't be explained by "the opponent's serve
    // faulted", since A wasn't receiving. This must fall through to a
    // genuine conflict instead of being read as a fault.
    const { fixture, courtAreaEl } = setup(participants, 'A', 'A');

    tap(courtAreaEl, 140, 75); // same short-serve-fault-zone landing as above
    fixture.detectChanges();

    expect(nicknames(scoringButtons(fixture))).toEqual([]);
    expect(nicknames(losingButtons(fixture))).toEqual([]);
    expect(fixture.nativeElement.querySelector('.status-badge')).toBeNull();
    expect(fixture.nativeElement.querySelector('.hint--warning')).not.toBeNull();
  });

  it('still treats it as a fault when the credited side was receiving (servingTeam is the other team)', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A', 'B');

    tap(courtAreaEl, 140, 75);
    fixture.detectChanges();

    expect(nicknames(scoringButtons(fixture))).toEqual(['陳甲', '劉乙']);
    expect(fixture.nativeElement.querySelector('.status-badge')).not.toBeNull();
  });

  it('still conflicts for the identical deep landing in a singles match (no long-fault zone)', () => {
    const { fixture, courtAreaEl } = setup(singlesParticipants, 'A');

    // Singles serves are legal all the way to the baseline, so x=0.03 on
    // A's own half is just a normal deep landing spot, not a fault
    // exemption — still contradicts A having been credited the point.
    tap(courtAreaEl, 56, 75);
    fixture.detectChanges();

    expect(nicknames(scoringButtons(fixture))).toEqual([]);
    expect(nicknames(losingButtons(fixture))).toEqual([]);
    expect(fixture.nativeElement.querySelector('.hint--warning')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.status-badge')).toBeNull();
  });

  it('keeps the fixed pools when an in-bounds landing falls on the opposing half', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A');

    // (200, 75) -> x=0.75 (B's half) — consistent with A already scoring.
    tap(courtAreaEl, 200, 75);
    fixture.detectChanges();

    expect(nicknames(scoringButtons(fixture))).toEqual(['陳甲', '劉乙']);
    expect(nicknames(losingButtons(fixture))).toEqual(['徐丙', '李丁']);
    expect(fixture.nativeElement.querySelector('.hint--warning')).toBeNull();
    expect(fixture.nativeElement.querySelector('.status-badge')).toBeNull();
  });

  it('an out-of-bounds landing never conflicts, regardless of the credited side', () => {
    const { fixture, courtAreaEl } = setup(participants, 'B');

    tap(courtAreaEl, 20, 10); // well outside the court on both axes
    fixture.detectChanges();

    expect(nicknames(scoringButtons(fixture))).toEqual(['徐丙', '李丁']);
    expect(nicknames(losingButtons(fixture))).toEqual(['陳甲', '劉乙']);
    expect(fixture.nativeElement.querySelector('.hint--warning')).toBeNull();
  });

  it('clears a scoring/losing pick that becomes inconsistent after the landing changes', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A');

    tap(courtAreaEl, 200, 75); // B's half -> consistent with A credited
    fixture.detectChanges();
    scoringButtons(fixture)[0].click(); // p1
    fixture.detectChanges();
    losingButtons(fixture)[0].click(); // p3
    fixture.detectChanges();
    expect(fixture.componentInstance.selectedRosterEntryId()).toBe('p1');
    expect(fixture.componentInstance.selectedLosingRosterEntryId()).toBe('p3');

    // Now land on A's own half instead -> contradicts A already crediting,
    // so both prior picks (now outside their emptied pools) are cleared.
    tap(courtAreaEl, 100, 75);
    fixture.detectChanges();

    expect(fixture.componentInstance.selectedRosterEntryId()).toBeNull();
    expect(fixture.componentInstance.selectedLosingRosterEntryId()).toBeNull();
  });

  // --- Long-press magnifier -------------------------------------------

  it('does not raise the magnifier for a quick tap', () => {
    const { fixture, courtAreaEl } = setup();

    tap(courtAreaEl, 150, 75);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.magnifier')).toBeNull();
  });

  it('raises the magnifier once the press is held past the long-press threshold', () => {
    vi.useFakeTimers();
    try {
      const { fixture, courtAreaEl } = setup();

      pointerDown(courtAreaEl, 150, 75);
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.magnifier')).toBeNull();

      vi.advanceTimersByTime(400);
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.magnifier')).not.toBeNull();

      pointerUp(courtAreaEl, 150, 75);
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.magnifier')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps the point (and magnifier) following the finger while dragging during a long press', () => {
    vi.useFakeTimers();
    try {
      // Team B credited -> landing on A's half (x<0.5) is consistent.
      const { fixture, courtAreaEl } = setup(participants, 'B');
      const confirmedSpy = vi.fn();
      fixture.componentInstance.confirmed.subscribe(confirmedSpy);

      pointerDown(courtAreaEl, 150, 75);
      vi.advanceTimersByTime(400);
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.magnifier')).not.toBeNull();

      // Drag from mid-court (150, 75 -> x/y 0.5/0.5) towards a corner.
      pointerMove(courtAreaEl, 60, 35);
      fixture.detectChanges();
      pointerUp(courtAreaEl, 60, 35);
      fixture.detectChanges();

      // (60,35) against rect left:50/top:25/width:200/height:100 -> x=0.05
      // (A's half) — consistent with B already credited.
      scoringButtons(fixture)[0].click(); // p3, team B
      fixture.detectChanges();
      losingButtons(fixture)[0].click(); // p1, team A
      fixture.detectChanges();
      fixture.nativeElement.querySelector('.actions button:last-of-type').click();

      expect(confirmedSpy).toHaveBeenCalledTimes(1);
      const { landingX, landingY } = confirmedSpy.mock.calls[0][0];
      expect(landingX).toBeCloseTo(0.05, 5);
      expect(landingY).toBeCloseTo(0.1, 5);
    } finally {
      vi.useRealTimers();
    }
  });

  // --- 032-out-of-bounds-by-match-mode: singles uses the narrower sideline -

  it('never conflicts for a singles match when the landing is beyond the singles sideline', () => {
    const { fixture, courtAreaEl } = setup(singlesParticipants, 'A');

    // .court's mocked rect is left:50/top:25/width:200/height:100 —
    // (100, 28) -> x=0.25 (A's own half), y=0.03: inside the doubles width
    // but outside the singles sideline (~0.0754), so for a 2-player match
    // this counts as out-of-bounds and never conflicts with A being credited.
    tap(courtAreaEl, 100, 28);
    fixture.detectChanges();

    expect(nicknames(scoringButtons(fixture))).toEqual(['陳甲']);
    expect(nicknames(losingButtons(fixture))).toEqual(['徐丙']);
  });

  it('the identical landing is in-bounds for a doubles match and can conflict there', () => {
    const { fixture, courtAreaEl } = setup(participants, 'A'); // doubles fixture, A credited

    tap(courtAreaEl, 100, 28); // same x=0.25, y=0.03 as above, but in-bounds for doubles

    fixture.detectChanges();

    // x=0.25 is A's own half -> contradicts A already being credited.
    expect(nicknames(scoringButtons(fixture))).toEqual([]);
    expect(nicknames(losingButtons(fixture))).toEqual([]);
  });

  // --- singles pre-selects the sole player on each side -------------------

  it('pre-selects the only possible scoring and losing player in a singles match, with no tap needed', () => {
    const { fixture } = setup(singlesParticipants, 'A');

    const selected = fixture.nativeElement.querySelectorAll('.player--selected');
    expect(Array.from(selected).map((el) => (el as HTMLElement).textContent?.trim())).toEqual([
      '陳甲',
      '徐丙',
    ]);
  });

  it('confirm() in a singles match sends both players without the scorer picking either', () => {
    const { fixture, courtAreaEl } = setup(singlesParticipants, 'A');
    const confirmedSpy = vi.fn();
    fixture.componentInstance.confirmed.subscribe(confirmedSpy);

    tap(courtAreaEl, 200, 75); // x=0.75, B's half — consistent with A credited
    fixture.detectChanges();
    fixture.nativeElement.querySelector('.actions button:last-of-type').click();

    expect(confirmedSpy).toHaveBeenCalledWith({
      rosterEntryId: 'p1',
      losingRosterEntryId: 'p3',
      landingX: 0.75,
      landingY: 0.5,
      endingType: null,
    });
  });

  it('still lets the scorer override the pre-selected singles player', () => {
    // A degenerate case (a "singles" match somehow has 2 players still
    // listed on one team) but confirms the pre-select never locks the pick.
    const threePlayers: ParticipantSummary[] = [
      { roster_entry_id: 'p1', nickname: '陳甲', team: 'A' },
      { roster_entry_id: 'p2', nickname: '劉乙', team: 'A' },
      { roster_entry_id: 'p3', nickname: '徐丙', team: 'B' },
    ];
    const { fixture } = setup(threePlayers, 'A');

    // Team B's pool has exactly one player (p3) and is pre-selected...
    expect(nicknames(losingButtons(fixture))).toEqual(['徐丙']);
    expect(fixture.nativeElement.querySelectorAll('.player--selected')[0].textContent?.trim()).toBe(
      '徐丙',
    );
    // ...but team A's pool has two, so nothing is pre-selected there, and a
    // manual pick still works normally.
    expect(fixture.nativeElement.querySelectorAll('.player--selected').length).toBe(1);
    scoringButtons(fixture)[1].click(); // p2
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.player--selected').length).toBe(2);
  });

  it('re-opening the dialog re-selects the sole singles player after the reset', () => {
    const { fixture } = setup(singlesParticipants, 'A');

    scoringButtons(fixture)[0].click(); // already pre-selected, but exercise a real pick too
    fixture.detectChanges();

    fixture.componentInstance.open();
    fixture.detectChanges();

    const selected = fixture.nativeElement.querySelectorAll('.player--selected');
    expect(Array.from(selected).map((el) => (el as HTMLElement).textContent?.trim())).toEqual([
      '陳甲',
      '徐丙',
    ]);
  });

  it('shades the out-of-play strip for a singles match', () => {
    const { fixture } = setup(singlesParticipants);
    expect(fixture.nativeElement.querySelectorAll('.out-of-play-band').length).toBe(2);
  });

  it('does not shade an out-of-play strip for a doubles match', () => {
    const { fixture } = setup();
    expect(fixture.nativeElement.querySelectorAll('.out-of-play-band').length).toBe(0);
  });

  // --- 032: responsive tab layout on a screen too short for everything ----

  describe('tab layout', () => {
    function mockLayout(
      fixture: { nativeElement: HTMLElement },
      { innerHeight, dialogHeight, contentClientHeight, contentScrollHeight }: {
        innerHeight: number;
        dialogHeight: number;
        contentClientHeight: number;
        contentScrollHeight: number;
      },
    ): void {
      vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(innerHeight);
      const dialogEl = fixture.nativeElement.querySelector('.shot-placement-dialog') as HTMLElement;
      vi.spyOn(dialogEl, 'getBoundingClientRect').mockReturnValue({
        height: dialogHeight,
        width: 0, top: 0, left: 0, right: 0, bottom: 0, x: 0, y: 0, toJSON: () => '',
      });
      const contentEl = fixture.nativeElement.querySelector('.content') as HTMLElement;
      Object.defineProperty(contentEl, 'clientHeight', {
        value: contentClientHeight, configurable: true,
      });
      Object.defineProperty(contentEl, 'scrollHeight', {
        value: contentScrollHeight, configurable: true,
      });
    }

    it('switches to a two-tab layout when the full content would not fit the screen', async () => {
      const { fixture } = setup();
      mockLayout(fixture, {
        innerHeight: 400,
        dialogHeight: 900,
        contentClientHeight: 700,
        contentScrollHeight: 900,
      });

      fixture.componentInstance.open();
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      fixture.detectChanges();

      expect(fixture.componentInstance.useTabs()).toBe(true);
      expect(fixture.componentInstance.activeTab()).toBe('landing');
      const tabs = fixture.nativeElement.querySelectorAll('.tab');
      expect(tabs.length).toBe(2);
      expect((fixture.nativeElement.querySelector('.players-section') as HTMLElement).hidden).toBe(
        true,
      );
      expect((fixture.nativeElement.querySelector('.landing-section') as HTMLElement).hidden).toBe(
        false,
      );

      (tabs[1] as HTMLButtonElement).click();
      fixture.detectChanges();
      expect((fixture.nativeElement.querySelector('.players-section') as HTMLElement).hidden).toBe(
        false,
      );
      expect((fixture.nativeElement.querySelector('.landing-section') as HTMLElement).hidden).toBe(
        true,
      );
    });

    it('keeps the single-column layout when everything fits the screen', async () => {
      const { fixture } = setup();
      mockLayout(fixture, {
        innerHeight: 1000,
        dialogHeight: 500,
        contentClientHeight: 400,
        contentScrollHeight: 400,
      });

      fixture.componentInstance.open();
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      fixture.detectChanges();

      expect(fixture.componentInstance.useTabs()).toBe(false);
      expect(fixture.nativeElement.querySelector('.tabs')).toBeNull();
    });
  });

  // --- 035-point-ending-type: the "how did the rally end" chip row --------

  describe('ending type', () => {
    /** The chip row lives in .landing-section, under the court; chips are
     * in ENDING_TYPES order (component.html). */
    function chips(fixture: { nativeElement: HTMLElement }): HTMLButtonElement[] {
      return Array.from(
        fixture.nativeElement.querySelectorAll<HTMLButtonElement>('.landing-section .ending-chip'),
      );
    }
    function chip(fixture: { nativeElement: HTMLElement }, kind: EndingType): HTMLButtonElement {
      return chips(fixture)[ENDING_TYPES.indexOf(kind)];
    }
    function pressed(fixture: { nativeElement: HTMLElement }): EndingType[] {
      return ENDING_TYPES.filter((kind) => chip(fixture, kind).getAttribute('aria-pressed') === 'true');
    }
    function disabled(fixture: { nativeElement: HTMLElement }): EndingType[] {
      return ENDING_TYPES.filter((kind) => chip(fixture, kind).getAttribute('aria-disabled') === 'true');
    }
    const confirmButton = (fixture: { nativeElement: HTMLElement }): HTMLButtonElement =>
      fixture.nativeElement.querySelector('.actions button:last-of-type') as HTMLButtonElement;

    it('renders the five kinds as chips in their fixed order, all enabled and none pressed, with no landing (d)', () => {
      const { fixture } = setup(participants, 'A');

      expect(chips(fixture).length).toBe(ENDING_TYPES.length);
      expect(pressed(fixture)).toEqual([]);
      expect(disabled(fixture)).toEqual([]);
      expect(fixture.componentInstance.endingType()).toBeNull();
    });

    it('auto-fills "out" and disables "winner" for an out-of-bounds landing (a)', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A');

      tap(courtAreaEl, 20, 10); // outside the mocked court on both axes
      fixture.detectChanges();

      expect(fixture.componentInstance.endingType()).toBe('out');
      expect(pressed(fixture)).toEqual(['out']);
      expect(disabled(fixture)).toEqual(['winner']);
    });

    it('auto-fills "serve_fault" for a serve-fault landing on the credited side\'s own half (b)', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A', 'B'); // A receiving

      tap(courtAreaEl, 140, 75); // x=0.45, short-serve-fault zone of A
      fixture.detectChanges();

      expect(fixture.componentInstance.isServeFault()).toBe(true);
      expect(fixture.componentInstance.endingType()).toBe('serve_fault');
      expect(pressed(fixture)).toEqual(['serve_fault']);
    });

    it('auto-fills nothing for an in-bounds landing on the loser\'s half and disables only "out" (c, SC-006)', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A');

      tap(courtAreaEl, 200, 75); // x=0.75, B's half — A credited
      fixture.detectChanges();

      expect(fixture.componentInstance.endingType()).toBeNull();
      expect(pressed(fixture)).toEqual([]);
      expect(disabled(fixture)).toEqual(['out']);
      // Still one tap away from either reading of that landing.
      chip(fixture, 'winner').click();
      fixture.detectChanges();
      expect(fixture.componentInstance.endingType()).toBe('winner');
    });

    // (c2) The in/out boundary vectors — the SAME table as the backend's
    // BOUNDS_VECTORS in tests/unit/domains/schedule/test_shot_placement.py
    // (035 data-model.md「界內／界外的邊界測試向量」). The two sides judge
    // "in bounds" independently (this component's landingSide() and
    // attach_shot_placement()'s check); a point they disagree on would let
    // the picker auto-fill a value the server then refuses, silently
    // losing the whole row. Keep both copies identical.
    const INSET = 0.46 / 6.1;
    const BOUNDS_VECTORS: [mode: 'doubles' | 'singles', x: number, y: number, inBounds: boolean][] = [
      ['doubles', 0.0, 0.5, true],
      ['doubles', 1.0, 0.5, true],
      ['doubles', 0.5, 0.0, true],
      ['doubles', 0.5, 1.0, true],
      ['doubles', -0.0001, 0.5, false],
      ['doubles', 1.0001, 0.5, false],
      ['doubles', 0.5, -0.0001, false],
      ['doubles', 0.5, 1.0001, false],
      ['singles', 0.5, INSET, true],
      ['singles', 0.5, 1 - INSET, true],
      ['singles', 0.5, INSET - 0.0001, false],
      ['singles', 0.5, 1 - INSET + 0.0001, false],
      ['singles', 0.5, 0.03, false],
    ];

    it.each(BOUNDS_VECTORS)(
      'judges (%s, x=%d, y=%d) in-bounds=%s exactly like the backend (c2)',
      (mode, x, y, inBounds) => {
        // The credited side is whichever makes an in-bounds point land on
        // the LOSER's half (x=0.5 is B's half), so nothing else interferes.
        const { fixture } = setup(mode === 'singles' ? singlesParticipants : participants, 'A');

        fixture.componentInstance.selectedPoint.set({ x, y });
        fixture.detectChanges();

        if (inBounds) {
          expect(fixture.componentInstance.landingSide()).not.toBe('out');
          expect(disabled(fixture)).toEqual(['out']);
        } else {
          expect(fixture.componentInstance.landingSide()).toBe('out');
          expect(disabled(fixture)).toEqual(['winner']);
          expect(fixture.componentInstance.endingType()).toBe('out');
        }
      },
    );

    it('keeps a hand-picked kind when the landing moves somewhere that does not contradict it (e, FR-009)', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A');

      tap(courtAreaEl, 200, 75); // in bounds, B's half
      fixture.detectChanges();
      chip(fixture, 'net').click();
      fixture.detectChanges();
      expect(fixture.componentInstance.endingType()).toBe('net');

      tap(courtAreaEl, 20, 10); // out of bounds — auto would say 'out'
      fixture.detectChanges();

      expect(fixture.componentInstance.endingType()).toBe('net');
      expect(pressed(fixture)).toEqual(['net']);
    });

    it('clears a hand-picked "winner" once the landing moves out of bounds, falling back to the auto "out" (f)', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A');

      tap(courtAreaEl, 200, 75);
      fixture.detectChanges();
      chip(fixture, 'winner').click();
      fixture.detectChanges();
      expect(fixture.componentInstance.endingType()).toBe('winner');

      tap(courtAreaEl, 20, 10);
      fixture.detectChanges();

      expect(fixture.componentInstance.endingType()).toBe('out');
      expect(pressed(fixture)).toEqual(['out']);
      expect(confirmButton(fixture).disabled).toBe(false);
    });

    it('clears a hand-picked "out" once the landing moves in bounds (f, the other direction)', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A');

      tap(courtAreaEl, 20, 10);
      fixture.detectChanges();
      chip(fixture, 'out').click(); // an explicit pick of the auto value
      fixture.detectChanges();

      tap(courtAreaEl, 200, 75);
      fixture.detectChanges();

      expect(fixture.componentInstance.endingType()).toBeNull();
      expect(pressed(fixture)).toEqual([]);
    });

    it('tapping the pressed chip again unselects it, and the auto-fill no longer overrides that (g)', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A');

      tap(courtAreaEl, 20, 10); // auto 'out'
      fixture.detectChanges();
      chip(fixture, 'out').click();
      fixture.detectChanges();

      expect(fixture.componentInstance.endingType()).toBeNull();
      expect(pressed(fixture)).toEqual([]);

      tap(courtAreaEl, 30, 10); // still out of bounds — auto would say 'out' again
      fixture.detectChanges();
      expect(fixture.componentInstance.endingType()).toBeNull();
    });

    it('a disabled chip cannot be picked', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A');

      tap(courtAreaEl, 20, 10);
      fixture.detectChanges();
      chip(fixture, 'winner').click();
      fixture.detectChanges();

      expect(fixture.componentInstance.endingType()).toBe('out');
    });

    it('disables "serve_fault" when the credited side was serving, even with no landing', () => {
      const { fixture } = setup(participants, 'A', 'A');

      expect(disabled(fixture)).toEqual(['serve_fault']);
      chip(fixture, 'serve_fault').click();
      fixture.detectChanges();
      expect(fixture.componentInstance.endingType()).toBeNull();
    });

    it('disables "serve_fault" alongside "out" for a serving side\'s in-bounds landing on the loser\'s half', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A', 'A');

      tap(courtAreaEl, 160, 75); // x=0.55, B's half — the reported case
      fixture.detectChanges();

      expect(disabled(fixture)).toEqual(['out', 'serve_fault']);
    });

    it('keeps "serve_fault" available when the credited side was receiving, or the server is unknown', () => {
      for (const serving of ['B', null] as const) {
        TestBed.resetTestingModule();
        const { fixture } = setup(participants, 'A', serving);
        expect(disabled(fixture)).toEqual([]);
      }
    });

    it('confirm() emits the effective kind, or null when nothing is selected (h)', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A');
      const confirmedSpy = vi.fn();
      fixture.componentInstance.confirmed.subscribe(confirmedSpy);

      confirmButton(fixture).click();
      expect(confirmedSpy).toHaveBeenLastCalledWith(
        expect.objectContaining({ endingType: null, landingX: null }),
      );

      fixture.componentInstance.open();
      tap(courtAreaEl, 20, 10); // auto 'out'
      fixture.detectChanges();
      confirmButton(fixture).click();
      expect(confirmedSpy).toHaveBeenLastCalledWith(expect.objectContaining({ endingType: 'out' }));

      fixture.componentInstance.open();
      tap(courtAreaEl, 200, 75);
      fixture.detectChanges();
      chip(fixture, 'other_error').click();
      fixture.detectChanges();
      confirmButton(fixture).click();
      expect(confirmedSpy).toHaveBeenLastCalledWith(
        expect.objectContaining({ endingType: 'other_error', landingX: 0.75 }),
      );
    });

    it('open() resets the hand-picked kind (i)', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A');

      tap(courtAreaEl, 200, 75);
      fixture.detectChanges();
      chip(fixture, 'net').click();
      fixture.detectChanges();

      fixture.componentInstance.open();
      fixture.detectChanges();

      expect(fixture.componentInstance.endingType()).toBeNull();
      expect(pressed(fixture)).toEqual([]);
    });

    it('shows a hint while the kind is auto-filled, not once it is hand-picked (j)', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A');
      const hint = (): Element | null => fixture.nativeElement.querySelector('.ending-auto-hint');

      expect(hint()).toBeNull();
      tap(courtAreaEl, 20, 10);
      fixture.detectChanges();
      expect(hint()).not.toBeNull();

      chip(fixture, 'net').click();
      fixture.detectChanges();
      expect(hint()).toBeNull();
    });

    it('keeps the chips inside the landing tab and the tab count at 2 in the tab layout (k)', async () => {
      const { fixture } = setup();
      vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(400);
      const dialogEl = fixture.nativeElement.querySelector('.shot-placement-dialog') as HTMLElement;
      vi.spyOn(dialogEl, 'getBoundingClientRect').mockReturnValue({
        height: 900, width: 0, top: 0, left: 0, right: 0, bottom: 0, x: 0, y: 0, toJSON: () => '',
      });
      const contentEl = fixture.nativeElement.querySelector('.content') as HTMLElement;
      Object.defineProperty(contentEl, 'clientHeight', { value: 700, configurable: true });
      Object.defineProperty(contentEl, 'scrollHeight', { value: 900, configurable: true });

      fixture.componentInstance.open();
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      fixture.detectChanges();

      expect(fixture.componentInstance.useTabs()).toBe(true);
      expect(fixture.nativeElement.querySelectorAll('.tab').length).toBe(2);
      expect(chips(fixture).length).toBe(ENDING_TYPES.length);
      expect(fixture.nativeElement.querySelectorAll('.players-section .ending-chip').length).toBe(0);
    });

    // --- landingConflict: no ending type explains a landing that
    // contradicts who was credited the point (not even "serve_fault" when
    // the credited side was itself serving — a fault always favors the
    // RECEIVER, never the server) -------------------------------------

    it('disables every chip when the credited side was serving and the landing lands on its own half', () => {
      // A serves and A is credited the point, but the landing is on A's own
      // half — official rules say A failed to return it, and it can't be a
      // serve fault either (A was serving, not receiving), so this is a
      // genuine contradiction, not a fault (component.ts's isServeFault()).
      const { fixture, courtAreaEl } = setup(participants, 'A', 'A');

      tap(courtAreaEl, 100, 75); // x=0.25, A's own half

      fixture.detectChanges();

      expect(fixture.componentInstance.landingConflict()).toBe(true);
      expect(fixture.componentInstance.isServeFault()).toBe(false);
      expect(disabled(fixture)).toEqual([...ENDING_TYPES]);
      expect(pressed(fixture)).toEqual([]);
      expect(fixture.componentInstance.endingType()).toBeNull();
      expect(confirmButton(fixture).disabled).toBe(true);
    });

    it('shows the landing-conflict warning on the landing tab itself, not only on the players tab', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A', 'A');

      tap(courtAreaEl, 100, 75);
      fixture.detectChanges();

      const landingSection = fixture.nativeElement.querySelector('.landing-section')!;
      expect(landingSection.querySelector('[data-landing-conflict]')).not.toBeNull();
      expect(landingSection.textContent).toContain('shotPlacement.landingConflict');
    });

    it('a chip disabled by a landing conflict cannot be picked either', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A', 'A');

      tap(courtAreaEl, 100, 75);
      fixture.detectChanges();
      chip(fixture, 'net').click();
      fixture.detectChanges();

      expect(fixture.componentInstance.endingType()).toBeNull();
    });

    it('clears a hand-picked kind once the landing changes into a conflict, same as the player picks', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A', 'A');

      tap(courtAreaEl, 200, 75); // B's half — consistent with A credited
      fixture.detectChanges();
      chip(fixture, 'winner').click();
      fixture.detectChanges();
      expect(fixture.componentInstance.endingType()).toBe('winner');

      tap(courtAreaEl, 100, 75); // now A's own half — a conflict
      fixture.detectChanges();

      expect(fixture.componentInstance.endingType()).toBeNull();
      expect(pressed(fixture)).toEqual([]);
    });

    it('re-enables the chips once the landing moves back out of conflict (only "serve_fault" stays off: A served)', () => {
      const { fixture, courtAreaEl } = setup(participants, 'A', 'A');

      tap(courtAreaEl, 100, 75); // conflict
      fixture.detectChanges();
      expect(disabled(fixture)).toEqual([...ENDING_TYPES]);

      tap(courtAreaEl, 200, 75); // B's half — consistent again
      fixture.detectChanges();

      expect(fixture.componentInstance.landingConflict()).toBe(false);
      expect(disabled(fixture)).toEqual(['out', 'serve_fault']);
    });
  });
});
