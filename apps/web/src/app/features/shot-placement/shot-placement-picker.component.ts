import {
  Component,
  DestroyRef,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ParticipantSummary, Team } from '../../core/api/court-live-state.models';
import { CourtDiagramComponent } from '../../core/court-diagram/court-diagram.component';

/** 032-optional-shot-placement-detail: every field is independently
 * optional — confirm() sends whatever the scorer actually picked, never
 * forcing all three to be filled in before submitting anything. */
export interface ShotPlacementConfirmed {
  rosterEntryId: string | null;
  losingRosterEntryId: string | null;
  landingX: number | null;
  landingY: number | null;
}

/** 031-shot-placement-scoring: shared "tap the court, pick the scoring
 * player, confirm" interaction — a single component reused by the
 * scoreboard, control panel, and all-courts control panel (research.md
 * Decision 2) instead of three separate implementations.
 *
 * 032-score-then-record: pressing "+" now applies the point immediately
 * (a plain +1, so match pace never waits on this dialog) — by the time this
 * opens, WHICH side scored is already decided and given via `scoringTeam`
 * (set by the caller right before calling open()); this UI only records
 * supplementary detail (exact landing spot, and which specific player on
 * each side was involved) for that already-applied point.
 *
 * Coordinate system: data-model.md Decision 1 — x in [0, 1] spans A's
 * baseline (0) to B's baseline (1), net at 0.5; y in [0, 1] spans one
 * sideline to the other. FR-010 requires marking a landing OUTSIDE the
 * court too (an out shot) — the template's `.court-area` (the actual
 * pointer/keyboard target) has a margin around the drawn `.court` rectangle
 * for exactly that; the pointer handlers below still measure against
 * `.court`'s own box, so a tap in that margin yields x/y outside [0, 1] on
 * its own. The `LANDING_RANGE` clamp only guards the edge of that margin
 * against the server's accepted range — it is not what makes out-of-bounds
 * possible. */
const LANDING_RANGE = { min: -0.3, max: 1.3 };

// 032-out-of-bounds-by-match-mode: the singles sideline is inset 0.46m from
// each doubles sideline (the drawn court's own border, y=0/1) out of the
// 6.1m doubles width — same proportion used to draw the singles sideline on
// the court diagram itself (shot-placement-picker.component.scss).
const SINGLES_SIDELINE_INSET = 0.46 / 6.1;

// 032-serve-fault-landing: a serve that lands on the CREDITED side's own
// half isn't necessarily a contradiction — it's exactly what a service
// fault looks like (the serve never legally reached the receiver's box),
// and the receiver (the credited side) wins the point immediately
// regardless of where the shuttle actually came down. These two bands,
// measured from each baseline, mark landings that could be such a fault
// rather than a genuine rally return-failure:
//   - short (never crossed the short service line): 1.98m from the net ->
//     4.72/13.4 from each baseline.
//   - long, DOUBLES ONLY (past the doubles long service line): 0.76/13.4
//     from each baseline. Singles serves are legal all the way to the
//     baseline, so there is no long-fault band for singles.
const SHORT_SERVICE_LINE_INSET = 4.72 / 13.4;
const LONG_SERVICE_LINE_INSET = 0.76 / 13.4;

// A precise tap on a phone screen is hard when a fingertip covers the exact
// spot being aimed at — holding past this threshold (without releasing)
// reveals a magnified, offset view of the court around the finger so the
// scorer can see (and keep adjusting) exactly where the point will land
// before lifting. A quick tap/click never reaches this threshold, so it
// keeps behaving exactly like a plain single click always did.
const LONG_PRESS_MS = 350;
const MAGNIFIER_DIAMETER_PX = 110;
const MAGNIFIER_ZOOM = 2.5;
// How far above the finger the lens floats — clear of the fingertip itself,
// which would otherwise cover the very thing being magnified.
const MAGNIFIER_VERTICAL_OFFSET_PX = 90;

@Component({
  selector: 'app-shot-placement-picker',
  imports: [TranslatePipe, CourtDiagramComponent],
  templateUrl: './shot-placement-picker.component.html',
  styleUrl: './shot-placement-picker.component.scss',
})
export class ShotPlacementPickerComponent {
  readonly participants = input.required<ParticipantSummary[]>();
  /** 032-score-then-record: which team was already credited the point
   * (fixed before this dialog ever opens — see the class doc comment). */
  readonly scoringTeam = input.required<Team>();
  /** Who was serving THIS rally, captured by the caller from the match's
   * live serve state right before the point was applied (not after — the
   * winner always serves next in badminton, so a post-point reading would
   * always equal `scoringTeam` and could never distinguish anything).
   * `null` for a match with no serve-state at all (created before
   * 030-score-serve-record) — `isServeFault` below falls back to its
   * pre-existing, ungated behavior in that case rather than assuming an
   * answer it doesn't have. */
  readonly servingTeam = input<Team | null>(null);
  readonly confirmed = output<ShotPlacementConfirmed>();
  /** 032-cancel-score: the caller applies the matching -1 correction — this
   * component never touches the score itself, only requests it. */
  readonly scoreCancelled = output<void>();
  /** 032-freeze-while-picker-open: fires whenever the dialog actually
   * closes, regardless of which of confirm/skip/cancelScore triggered
   * it — a caller freezing its own display while this is open (so a
   * match-ending point's realtime refresh can't tear this dialog's DOM out
   * from under the scorer) uses this as the single signal to lift that
   * freeze again. */
  readonly closed = output<void>();

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  // 032-match-record-scoring-stats: `#court` is now the <app-court-diagram>
  // host element itself (research.md Decision 5) — `{ read: ElementRef }`
  // resolves it to the native element (its bounding box, unchanged) rather
  // than the component instance, which is what viewChild would give by
  // default for a component-tagged template reference.
  private readonly court = viewChild.required<string, ElementRef<HTMLElement>>('court', {
    read: ElementRef,
  });
  private readonly content = viewChild.required<ElementRef<HTMLDivElement>>('content');

  readonly selectedPoint = signal<{ x: number; y: number } | null>(null);
  readonly selectedRosterEntryId = signal<string | null>(null);
  readonly selectedLosingRosterEntryId = signal<string | null>(null);
  /** Official badminton rule (spec 032): an in-bounds landing on one half of
   * the court means that side failed to return the shuttle, so the OTHER
   * side is the one that scores — 'A' means x is in A's half (x<0.5, since
   * data-model.md Decision 1 puts A's baseline at x=0), 'B' the other half,
   * 'out' when the point isn't decided by which half it landed in (the
   * shuttle never landed in either court, so either team could be at
   * fault).
   *
   * 032-out-of-bounds-by-match-mode: "in bounds" itself follows official
   * rules — a singles rally only counts inside the narrower singles
   * sideline, not the full doubles width, same as a real singles match.
   * Singles vs. doubles is derived from how many players are actually on
   * this match (participants().length) rather than a separate input, since
   * that's already the authoritative source the picker is given. */
  readonly isSinglesMatch = computed(() => this.participants().length <= 2);
  readonly landingSide = computed<Team | 'out' | null>(() => {
    const point = this.selectedPoint();
    if (point === null) {
      return null;
    }
    const [yMin, yMax] = this.isSinglesMatch()
      ? [SINGLES_SIDELINE_INSET, 1 - SINGLES_SIDELINE_INSET]
      : [0, 1];
    const inBounds = point.x >= 0 && point.x <= 1 && point.y >= yMin && point.y <= yMax;
    if (!inBounds) {
      return 'out';
    }
    return point.x < 0.5 ? 'A' : 'B';
  });

  /** The scoring team is fixed by the caller (`scoringTeam` input) — the
   * losing team is simply the other one, always (only two teams exist). */
  private readonly losingTeamFixed = computed<Team>(() =>
    this.scoringTeam() === 'A' ? 'B' : 'A',
  );

  /** True whenever the landing is in-bounds on the credited side's OWN
   * half — the precondition shared by `isServeFault` and `landingConflict`
   * below (an in-bounds landing anywhere else, or out of bounds, is never
   * either one). */
  private readonly landingOnCreditedSidesOwnHalf = computed(() => {
    const side = this.landingSide();
    return (side === 'A' || side === 'B') && side === this.scoringTeam();
  });

  /** True when a landing on the credited side's own half falls in a
   * serve-fault band (isServeFaultZone()) — the serve never legally
   * reached the receiver's box, so the credited side (the receiver) won
   * the point on a service fault, without ever having to return anything.
   * Surfaced in the template as a badge next to "select the losing player"
   * so the scorer understands why the pools below aren't empty despite the
   * landing being on their own side.
   *
   * A serve fault is only a coherent explanation when the credited side
   * was RECEIVING this rally — if `scoringTeam` was the one serving and
   * still won, there is no "my own serve faulted, so I win" reading
   * available; a landing that lands on their own half in that case is a
   * genuine data-entry contradiction instead (falls through to
   * `landingConflict` below), not a fault. */
  readonly isServeFault = computed(() => {
    const point = this.selectedPoint();
    if (!this.landingOnCreditedSidesOwnHalf() || point === null) {
      return false;
    }
    const serving = this.servingTeam();
    if (serving !== null && serving === this.scoringTeam()) {
      return false;
    }
    return this.isServeFaultZone(point.x, this.scoringTeam());
  });

  /** True once an in-bounds landing contradicts the already-credited side —
   * an in-bounds landing on team Z's half means Z failed to return it
   * (official badminton rules), so it's only consistent with `scoringTeam`
   * when Z is the OTHER team — UNLESS it's a serve fault instead (see
   * `isServeFault` above). Out-of-bounds never conflicts — it doesn't
   * reveal which side hit it out. Mirrors attach_shot_placement()'s
   * server-side check (service.py). */
  readonly landingConflict = computed(
    () => this.landingOnCreditedSidesOwnHalf() && !this.isServeFault(),
  );

  /** 032-optional-shot-placement-detail: confirm() no longer requires the
   * landing point AND both players to all be filled in — the scorer can
   * submit with only whatever they picked. The only thing that actually
   * blocks submission is a genuine data-integrity problem: the landing
   * contradicting the side that was already credited the point. */
  readonly canConfirm = computed(() => !this.landingConflict());

  private isServeFaultZone(x: number, side: Team): boolean {
    const isDoubles = !this.isSinglesMatch();
    if (side === 'A') {
      if (x > SHORT_SERVICE_LINE_INSET && x < 0.5) {
        return true;
      }
      return isDoubles && x < LONG_SERVICE_LINE_INSET;
    }
    if (x < 1 - SHORT_SERVICE_LINE_INSET && x > 0.5) {
      return true;
    }
    return isDoubles && x > 1 - LONG_SERVICE_LINE_INSET;
  }

  readonly scoringPlayers = computed(() =>
    this.landingConflict()
      ? []
      : this.participants().filter((p) => p.team === this.scoringTeam()),
  );
  readonly losingPlayers = computed(() =>
    this.landingConflict()
      ? []
      : this.participants().filter((p) => p.team === this.losingTeamFixed()),
  );

  readonly magnifierVisible = signal(false);
  readonly magnifierLensPosition = signal({ x: 0, y: 0 });
  /** The lens's inner content: a full-size copy of `.court` (same pixel
   * dimensions), scaled + translated so the currently-held point sits
   * exactly at the lens's center — computed here rather than duplicated
   * inline in the template. */
  readonly magnifierContentStyle = computed(() => {
    const point = this.selectedPoint();
    if (point === null) {
      return null;
    }
    const rect = this.court().nativeElement.getBoundingClientRect();
    const pointPxX = point.x * rect.width;
    const pointPxY = point.y * rect.height;
    const lensRadius = MAGNIFIER_DIAMETER_PX / 2;
    return {
      width: `${rect.width}px`,
      height: `${rect.height}px`,
      transform:
        `translate(${lensRadius}px, ${lensRadius}px) ` +
        `scale(${MAGNIFIER_ZOOM}) ` +
        `translate(${-pointPxX}px, ${-pointPxY}px)`,
    };
  });

  /** 032: on a small enough screen, the court + both player sections don't
   * all fit in the dialog at once — dynamically switch to a two-tab layout
   * ("landing point" / "scoring & fault players") instead of letting the
   * dialog scroll internally. Re-measured on open() and on window resize
   * (see the constructor); recomputeLayoutMode() temporarily forces the
   * full (non-tab) layout back on to measure whether it fits, so shrinking
   * the window back can also switch tabs back off. */
  readonly useTabs = signal(false);
  readonly activeTab = signal<'landing' | 'players'>('landing');
  /** Applied to `.content` only while `useTabs()` is true (component.ts
   * `recomputeLayoutMode()`) — caps even a single active tab's own content
   * to the space actually available, falling back to that tab's own
   * internal scroll (rather than pushing the always-visible Cancel/Confirm
   * actions off-screen) in the rare case one section alone still doesn't
   * fit. `null` removes the cap entirely, restoring natural sizing. */
  readonly contentMaxHeightPx = signal<number | null>(null);

  private longPressTimer?: ReturnType<typeof setTimeout>;
  private activePointerId: number | null = null;

  constructor() {
    // A landing change can make the currently-picked scoring/losing player
    // ineligible (e.g. the point moved from one half of the court to the
    // other, or in/out of bounds) — drop a pick the instant it falls
    // outside its own pool rather than leaving a stale, now-invalid
    // selection displayed as chosen. Conversely, in singles there's only
    // ever one possible player on each side (pool.length === 1) — tapping a
    // chip that has no real alternative is a needless step for the scorer,
    // so pre-select it the same way a genuine tap would, the moment the
    // pool settles on that single option (open()'s reset to null, or the
    // pool becoming valid again after a landing conflict clears, both flow
    // through here since both signals are read below).
    effect(() => {
      const pool = this.scoringPlayers();
      const id = this.selectedRosterEntryId();
      if (id !== null && !pool.some((p) => p.roster_entry_id === id)) {
        this.selectedRosterEntryId.set(null);
      } else if (id === null && pool.length === 1) {
        this.selectedRosterEntryId.set(pool[0].roster_entry_id);
      }
    });
    effect(() => {
      const pool = this.losingPlayers();
      const id = this.selectedLosingRosterEntryId();
      if (id !== null && !pool.some((p) => p.roster_entry_id === id)) {
        this.selectedLosingRosterEntryId.set(null);
      } else if (id === null && pool.length === 1) {
        this.selectedLosingRosterEntryId.set(pool[0].roster_entry_id);
      }
    });

    if (typeof window !== 'undefined') {
      window.addEventListener('resize', this.handleWindowResize);
      inject(DestroyRef).onDestroy(() => {
        window.removeEventListener('resize', this.handleWindowResize);
      });
    }
  }

  private readonly handleWindowResize = (): void => {
    if (this.dialog().nativeElement.open) {
      this.recomputeLayoutMode();
    }
  };

  open(): void {
    this.selectedPoint.set(null);
    this.selectedRosterEntryId.set(null);
    this.selectedLosingRosterEntryId.set(null);
    this.magnifierVisible.set(false);
    this.useTabs.set(false);
    this.activeTab.set('landing');
    this.contentMaxHeightPx.set(null);
    // jsdom (unit tests) doesn't implement <dialog> — same guard as
    // ConfirmDialogComponent.
    const nativeDialog = this.dialog().nativeElement;
    if (typeof nativeDialog.showModal === 'function') {
      nativeDialog.showModal();
    }
    // Measure after the dialog has actually laid out its (still untabbed)
    // content — a plain function call here would run before the browser
    // paints the newly-opened dialog.
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => this.recomputeLayoutMode());
    }
  }

  /** Decides whether the court + both player sections fit together, or
   * whether the dialog needs to switch to a two-tab layout instead.
   *
   * `contentEl.scrollHeight` always reports `.content`'s full natural
   * height (both sections' combined size) regardless of any max-height cap
   * already applied to it — the DOM's `scrollHeight` ignores clipping by
   * design — EXCEPT for a section currently hidden via the `[hidden]`
   * attribute (which removes it from layout entirely, contributing 0);
   * `.measuring-full` (see the stylesheet) temporarily overrides that so a
   * window enlarge can be detected too, not just a shrink.
   *
   * `chromeHeight` (h2 + tabs-bar-if-shown + actions + paddings) is derived
   * by subtracting `.content`'s own currently-rendered height from the
   * dialog's — since the dialog itself is never height-constrained, this
   * stays accurate whether or not a cap is currently applied to `.content`. */
  private recomputeLayoutMode(): void {
    const dialogEl = this.dialog().nativeElement;
    const contentEl = this.content().nativeElement;
    const wasTabs = this.useTabs();
    if (wasTabs) {
      contentEl.classList.add('measuring-full');
    }

    const chromeHeight = dialogEl.getBoundingClientRect().height - contentEl.clientHeight;
    const viewportBudget = Math.min(720, window.innerHeight * 0.92);
    const availableForContent = Math.max(0, viewportBudget - chromeHeight);
    const overflowing = contentEl.scrollHeight > availableForContent + 1;

    if (wasTabs) {
      contentEl.classList.remove('measuring-full');
    }

    this.useTabs.set(overflowing);
    this.contentMaxHeightPx.set(overflowing ? Math.floor(availableForContent) : null);
  }

  /** FR-003: re-pressing anywhere on the court (or its out-of-bounds
   * margin, `.court-area`) before confirming just replaces the pending
   * point — nothing is emitted/recorded until confirm(). A quick tap places
   * the point immediately, same as a plain click always did; holding past
   * LONG_PRESS_MS additionally raises the magnifier for fine-aiming (see
   * onCourtPointerMove()). */
  onCourtPointerDown(event: PointerEvent): void {
    event.preventDefault();
    this.activePointerId = event.pointerId;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    this.updatePointFromClient(event.clientX, event.clientY);

    clearTimeout(this.longPressTimer);
    this.longPressTimer = setTimeout(() => {
      this.magnifierVisible.set(true);
      this.updateMagnifierLensPosition(event.clientX, event.clientY);
    }, LONG_PRESS_MS);
  }

  /** While still pressed, keeps the pending point (and, once raised, the
   * magnifier lens) following the finger — this is what lets the scorer
   * drag to fine-tune the exact spot while watching the magnified view. */
  onCourtPointerMove(event: PointerEvent): void {
    if (this.activePointerId !== event.pointerId) {
      return;
    }
    this.updatePointFromClient(event.clientX, event.clientY);
    if (this.magnifierVisible()) {
      this.updateMagnifierLensPosition(event.clientX, event.clientY);
    }
  }

  onCourtPointerUp(event: PointerEvent): void {
    if (this.activePointerId !== event.pointerId) {
      return;
    }
    clearTimeout(this.longPressTimer);
    this.magnifierVisible.set(false);
    this.activePointerId = null;
  }

  /** Keyboard-accessible fallback for the pointer handlers above — a
   * free-form pointer coordinate has no natural keyboard equivalent, so
   * Enter/Space on the focused court area selects mid-court (0.5, 0.5) as a
   * usable default rather than leaving keyboard users with no way to
   * proceed. No magnifier involved — nothing to aim with a fingertip here. */
  pickCenterPoint(): void {
    this.selectedPoint.set({ x: 0.5, y: 0.5 });
  }

  /** FR-003: re-selecting another player before confirming just replaces
   * the pending choice. */
  pickScoringPlayer(rosterEntryId: string): void {
    this.selectedRosterEntryId.set(rosterEntryId);
  }

  pickLosingPlayer(rosterEntryId: string): void {
    this.selectedLosingRosterEntryId.set(rosterEntryId);
  }

  /** 032-optional-shot-placement-detail: sends whatever the scorer actually
   * picked — none of the three fields is required — the `[disabled]`
   * binding (canConfirm()) already keeps this from firing while the
   * landing contradicts the credited side; the guard here is just defense
   * in depth against a stale click. */
  confirm(): void {
    if (!this.canConfirm()) {
      return;
    }
    const point = this.selectedPoint();
    this.confirmed.emit({
      rosterEntryId: this.selectedRosterEntryId(),
      losingRosterEntryId: this.selectedLosingRosterEntryId(),
      landingX: point?.x ?? null,
      landingY: point?.y ?? null,
    });
    this.closeIfSupported();
  }

  /** Closes without recording ANY detail for this point — the score itself
   * was already applied (see the class doc comment) and is left exactly as
   * it is; only the supplementary landing/player detail is discarded, even
   * if some of it had already been picked. */
  skip(): void {
    this.closeIfSupported();
  }

  /** Undoes the point itself (the caller applies the matching -1
   * correction) — for when "+" was pressed by mistake (e.g. the wrong
   * team's button). Distinct from skip() above, which leaves the score
   * standing and only discards the detail. */
  cancelScore(): void {
    this.scoreCancelled.emit();
    this.closeIfSupported();
  }

  private updatePointFromClient(clientX: number, clientY: number): void {
    const rect = this.court().nativeElement.getBoundingClientRect();
    this.selectedPoint.set({
      x: this.clampToLandingRange((clientX - rect.left) / rect.width),
      y: this.clampToLandingRange((clientY - rect.top) / rect.height),
    });
  }

  private updateMagnifierLensPosition(clientX: number, clientY: number): void {
    this.magnifierLensPosition.set({ x: clientX, y: clientY - MAGNIFIER_VERTICAL_OFFSET_PX });
  }

  private clampToLandingRange(value: number): number {
    return Math.min(LANDING_RANGE.max, Math.max(LANDING_RANGE.min, value));
  }

  private closeIfSupported(): void {
    const nativeDialog = this.dialog().nativeElement;
    if (typeof nativeDialog.close === 'function') {
      nativeDialog.close();
    }
    this.closed.emit();
  }
}
