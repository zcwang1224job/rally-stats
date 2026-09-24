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
  untracked,
  viewChild,
} from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import {
  ENDING_TYPES,
  EndingType,
  ParticipantSummary,
  Team,
} from '../../core/api/court-live-state.models';
import { CourtDiagramComponent } from '../../core/court-diagram/court-diagram.component';
import { IconComponent } from '../../shared/icon/icon.component';

/** 032-optional-shot-placement-detail: every field is independently
 * optional — confirm() sends whatever the scorer actually picked, never
 * forcing all three to be filled in before submitting anything. */
export interface ShotPlacementConfirmed {
  rosterEntryId: string | null;
  losingRosterEntryId: string | null;
  landingX: number | null;
  landingY: number | null;
  /** 035-point-ending-type: the effective kind — auto-filled from the
   * landing or hand-picked (see `endingType` below) — or null when the
   * scorer left it unrecorded. */
  endingType: EndingType | null;
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

// A serve-fault landing sits on the CREDITED side's own half, so the credited
// side never returned it: its own winner can't have landed there, the loser
// netting it would have left it on the loser's side, and it is in bounds.
// Only the loser's fault — the serve itself, or some other fault — explains
// it. Mirrors service.py's _SERVE_FAULT_LANDING_CONTRADICTS.
const SERVE_FAULT_LANDING_CONTRADICTS: readonly EndingType[] = ['winner', 'out', 'net'];

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

// Mobile picker layout: the court is drawn at the same 2:1 box as every
// other court diagram in the app, measured here in "court units" (1 unit =
// 1/13.4 of the length) so the out-of-bounds margin and the half-court
// window can be laid out around it in plain percentages.
const COURT_LENGTH = 13.4;
const COURT_WIDTH = COURT_LENGTH / 2;
// Tappable out-of-bounds margin around the drawn court (FR-010) — the
// same role `.court-area`'s 6% padding used to play.
const OUT_MARGIN = 1;
// Compact (half-court) view only: how much of the hidden half stays in
// view past the net. That strip is the "switch to the other half" button,
// wide enough for a thumb, and keeps the front court next to the net
// itself (where net shots and kills land) free of any overlay.
const PEEK = 1.4;

// Phones get the half-court view: portrait below the tablet breakpoint
// (styles/_breakpoints.scss $breakpoint-tablet — the same width where
// dialog--xl turns full-screen), and short landscape (the same query the
// control panel's own compact landscape layout uses).
const COMPACT_VIEW_QUERY =
  '(max-width: 767.98px), (orientation: landscape) and (max-height: 500px)';

/** Which player group the current ending type makes the one worth asking
 * about: the scoring player for a winner, the player at fault for every
 * kind of error. `null` = no ending type yet, so both are asked. */
type PlayerRole = 'scoring' | 'losing';

export interface CourtViewGeometry {
  /** Width / height of the visible window. */
  aspect: number;
  courtLeftPct: number;
  courtTopPct: number;
  courtWidthPct: number;
  courtHeightPct: number;
  /** Compact view only: which edge holds the peek of the hidden half. */
  peekSide: 'left' | 'right' | null;
  peekWidthPct: number;
  outMarginTopPct: number;
}

@Component({
  selector: 'app-shot-placement-picker',
  imports: [TranslatePipe, CourtDiagramComponent, IconComponent],
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
  /** The serving team's own score BEFORE this point, captured alongside
   * `servingTeam`. Its parity says which service court the serve came
   * from (even: right, odd: left), and so which of the receiver's two
   * courts was the legal, diagonal target — see `isServeFaultZone`.
   * `null` when unknown; the left/right check is then skipped. */
  readonly servingScore = input<number | null>(null);
  /** The player who served THIS rally, captured with `servingTeam`. On a
   * serve fault the server is the player at fault, so it is pre-selected
   * as the losing player. `null` when unknown. */
  readonly servingRosterEntryId = input<string | null>(null);
  /** Which team the host screen currently draws on the left (the control
   * panels let the scorer swap sides). The court here is drawn the same
   * way round so a tap lands where the scorer sees it on the board.
   * Swapped sides are the court seen after the teams change ends — the
   * whole court turned around, so both x and y flip (the board's station
   * pills do the same, see ControlPanelComponent.serveRosterId). */
  readonly leftTeam = input<Team>('A');
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
  private readonly courtArea = viewChild.required<ElementRef<HTMLElement>>('courtArea');
  private readonly court = viewChild.required<string, ElementRef<HTMLElement>>('court', {
    read: ElementRef,
  });

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
  readonly losingTeam = computed<Team>(() => (this.scoringTeam() === 'A' ? 'B' : 'A'));

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
    return this.isServeFaultZone(point.x, point.y, this.scoringTeam());
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

  /** 035-point-ending-type: how the rally ended, one chip row under the
   * court. Two layers, hand-picked over auto-filled:
   *
   * - `manualEndingType` is what the scorer tapped. `undefined` = never
   *   touched (the auto-fill decides); `null` = tapped the pressed chip
   *   again to unselect — an explicit "not recorded" that the auto-fill
   *   MUST NOT quietly override afterwards (FR-009). A hand-pick survives
   *   re-tapping the landing, except when the new landing makes it
   *   self-contradicting (the effect in the constructor clears it back to
   *   `undefined`, so the auto-fill takes over again).
   * - `autoEndingType` follows the landing where it leaves no doubt:
   *   out of bounds → 'out'; a serve-fault landing → 'serve_fault'. An
   *   in-bounds landing on the loser's half is deliberately NOT read as
   *   'winner' — it looks the same as a net shot dropping on the hitter's
   *   own side (spec edge case), so that one stays a real tap (SC-006).
   *
   * `disabledEndingTypes` mirrors attach_shot_placement()'s contradiction
   * check (service.py, ENDING_TYPE_CONTRADICTS_LANDING) so a value the
   * server would refuse can't be picked here in the first place — the
   * callers drop a failed request silently, which would lose the whole
   * row. The in/out judgement itself is `landingSide()`, pinned to the
   * backend's by a shared boundary-vector table (035 data-model.md).
   *
   * `landingConflict()` takes priority over the plain in/out rule: e.g. A
   * serving and A already credited the point, with the landing on A's OWN
   * half, can never be explained by a serve fault either (a fault always
   * favors the RECEIVER — see `isServeFault`'s doc comment) — no ending
   * type is a valid explanation for a landing that contradicts who was
   * credited, so every chip is disabled until the landing itself is fixed,
   * matching the emptied player pools below.
   *
   * 'serve_fault' is also disabled whenever the credited side was the one
   * serving, landing or not — a fault always hands the point to the
   * RECEIVER (same gate as `isServeFault`, and the server's
   * ENDING_TYPE_CONTRADICTS_SERVE). */
  readonly endingTypes = ENDING_TYPES;
  readonly manualEndingType = signal<EndingType | null | undefined>(undefined);
  readonly autoEndingType = computed<EndingType | null>(() =>
    this.landingSide() === 'out' ? 'out' : this.isServeFault() ? 'serve_fault' : null,
  );
  readonly disabledEndingTypes = computed<readonly EndingType[]>(() => {
    if (this.landingConflict()) {
      return this.endingTypes;
    }
    if (this.isServeFault()) {
      return SERVE_FAULT_LANDING_CONTRADICTS;
    }
    const side = this.landingSide();
    const byLanding: EndingType[] = side === null ? [] : side === 'out' ? ['winner'] : ['out'];
    return this.servingTeam() === this.scoringTeam() ? [...byLanding, 'serve_fault'] : byLanding;
  });
  readonly endingType = computed<EndingType | null>(() => {
    const manual = this.manualEndingType();
    return manual === undefined ? this.autoEndingType() : manual;
  });
  /** True while the pressed chip came from the auto-fill rather than the
   * scorer's own tap — the template shows a short hint then, so it's
   * clear the value can still be changed. */
  readonly endingTypeIsAuto = computed(
    () => this.manualEndingType() === undefined && this.autoEndingType() !== null,
  );

  /** Whether an in-bounds landing on `side`'s (the receiver's) half is
   * outside the serve's legal target: short of the short service line,
   * past the doubles long service line, or — when the server's score is
   * known — in the wrong one of the receiver's two service courts. A serve
   * goes diagonally, and each side's right court is diagonal to the other
   * side's right court, so the target is the receiver's right court when
   * the server's score is even and its left court when odd. Teams face
   * each other, so A's right court is the bottom half (y > 0.5) and B's
   * the top half (y < 0.5) — the same convention as the station pills
   * (ControlPanelComponent.serveRosterId). The center line itself counts
   * as in, for both courts. Mirrors service.py's _is_serve_fault_zone(). */
  private isServeFaultZone(x: number, y: number, side: Team): boolean {
    const isDoubles = !this.isSinglesMatch();
    const depthFault =
      side === 'A'
        ? (x > SHORT_SERVICE_LINE_INSET && x < 0.5) || (isDoubles && x < LONG_SERVICE_LINE_INSET)
        : (x < 1 - SHORT_SERVICE_LINE_INSET && x > 0.5) ||
          (isDoubles && x > 1 - LONG_SERVICE_LINE_INSET);
    if (depthFault) {
      return true;
    }
    const serverScore = this.servingScore();
    if (serverScore === null || this.servingTeam() === null) {
      return false;
    }
    const targetIsRightCourt = serverScore % 2 === 0;
    const targetIsBottom = targetIsRightCourt === (side === 'A');
    return targetIsBottom ? y < 0.5 : y > 0.5;
  }

  readonly scoringPlayers = computed(() =>
    this.landingConflict()
      ? []
      : this.participants().filter((p) => p.team === this.scoringTeam()),
  );
  readonly losingPlayers = computed(() =>
    this.landingConflict()
      ? []
      : this.participants().filter((p) => p.team === this.losingTeam()),
  );

  readonly magnifierVisible = signal(false);
  readonly magnifierLensPosition = signal({ x: 0, y: 0 });
  /** The lens's inner content: a full-size copy of `.court` (same pixel
   * dimensions), scaled + translated so the currently-held point sits
   * exactly at the lens's center — computed here rather than duplicated
   * inline in the template. */
  readonly magnifierContentStyle = computed(() => {
    const point = this.displayPoint();
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

  /** Phones (COMPACT_VIEW_QUERY) show one half of the court, enlarged,
   * instead of the whole court: the half where this point most likely
   * landed, with a strip of the other half past the net to switch over.
   * Wider screens keep the whole court. Replaces the old measured
   * two-tab fallback: the layout itself (component.scss) now lets the
   * court shrink to whatever height is left, so everything fits on one
   * screen and the confirm button never needs scrolling to (035 FR-013). */
  readonly compactView = signal(false);
  /** The half the scorer switched to by hand; `null` = follow
   * `autoViewTeam`. Cleared again by picking an ending type. */
  readonly viewOverride = signal<Team | null>(null);
  /** Where the shuttle most likely came down, going by the ending type
   * the scorer tapped: out and serve faults land on the scoring side's
   * half (or beyond it); winners, net shots and other errors on the
   * losing side's half. Only a hand-picked type moves the view — an
   * auto-filled one comes from a landing the scorer already placed, and
   * flipping away from it would hide that very point. */
  readonly autoViewTeam = computed<Team>(() => {
    const manual = this.manualEndingType();
    return manual === 'out' || manual === 'serve_fault' ? this.scoringTeam() : this.losingTeam();
  });
  readonly viewTeam = computed<Team>(() => this.viewOverride() ?? this.autoViewTeam());
  /** Which side of the drawing the viewed half is on. */
  readonly viewSide = computed<'left' | 'right'>(() =>
    this.viewTeam() === this.leftTeam() ? 'left' : 'right',
  );
  /** True when the host draws B on the left: the court is shown turned
   * around (see `leftTeam`). */
  readonly rotated = computed(() => this.leftTeam() === 'B');
  /** `selectedPoint` as drawn. Everything recorded stays in the data
   * coordinates; only the drawing turns. */
  readonly displayPoint = computed(() => {
    const point = this.selectedPoint();
    if (point === null) {
      return null;
    }
    return this.rotated() ? { x: 1 - point.x, y: 1 - point.y } : point;
  });
  /** True when the picked point is on the half the compact view is not
   * showing — the switch strip then carries a dot so it isn't lost. */
  readonly pointOnHiddenHalf = computed(() => {
    const point = this.displayPoint();
    if (!this.compactView() || point === null) {
      return false;
    }
    return (point.x < 0.5 ? 'left' : 'right') !== this.viewSide();
  });

  /** Compact view only: an out-of-bounds landing on the losing side's end
   * of the court. The losing side hit the shot that went out, so it
   * almost always comes down past the SCORING side's lines — this usually
   * means the scorer tapped the margin of the half that happened to be in
   * view. Recorded as tapped (it's still a valid out), but flagged with a
   * one-tap way over to the other half. */
  readonly outOnLosingSide = computed(() => {
    const point = this.selectedPoint();
    if (!this.compactView() || point === null || this.landingSide() !== 'out') {
      return false;
    }
    return (point.x < 0.5 ? 'A' : 'B') === this.losingTeam();
  });

  /** Where the drawn court sits inside the visible window, in % of that
   * window, plus the window's own aspect ratio. Pointer math never uses
   * this: it measures the court's own box, so any window works. */
  readonly courtGeometry = computed<CourtViewGeometry>(() => {
    const viewHeight = OUT_MARGIN + COURT_WIDTH + OUT_MARGIN;
    const compact = this.compactView();
    const viewWidth = compact
      ? OUT_MARGIN + COURT_LENGTH / 2 + PEEK
      : OUT_MARGIN + COURT_LENGTH + OUT_MARGIN;
    // Right-hand half in view: put the net PEEK in from the left edge.
    const courtLeft = compact && this.viewSide() === 'right' ? PEEK - COURT_LENGTH / 2 : OUT_MARGIN;
    const pct = (value: number, of: number) => (value / of) * 100;
    return {
      aspect: viewWidth / viewHeight,
      courtLeftPct: pct(courtLeft, viewWidth),
      courtTopPct: pct(OUT_MARGIN, viewHeight),
      courtWidthPct: pct(COURT_LENGTH, viewWidth),
      courtHeightPct: pct(COURT_WIDTH, viewHeight),
      peekSide: compact ? (this.viewSide() === 'left' ? 'right' : 'left') : null,
      peekWidthPct: compact ? pct(PEEK, viewWidth) : 0,
      outMarginTopPct: pct(OUT_MARGIN, viewHeight),
    };
  });

  /** The team colour each visible baseline is edged with, so the scorer
   * can tell whose half they are looking at. */
  teamColor(team: Team): string {
    return team === 'A' ? 'var(--color-team-a-bg)' : 'var(--color-team-b-bg)';
  }
  readonly leftEdgeColor = computed<string | null>(() => {
    if (this.compactView()) {
      return this.viewSide() === 'left' ? this.teamColor(this.viewTeam()) : null;
    }
    return this.teamColor(this.leftTeam());
  });
  readonly rightEdgeColor = computed<string | null>(() => {
    if (this.compactView()) {
      return this.viewSide() === 'right' ? this.teamColor(this.viewTeam()) : null;
    }
    return this.teamColor(this.leftTeam() === 'A' ? 'B' : 'A');
  });

  /** One player group is enough once the ending type says who the rally
   * was about: the scoring player for a winner, the player at fault for
   * every error. The other group folds away behind a one-line toggle
   * (still one tap to open). With no ending type yet — or while the
   * landing conflicts — both groups show, as before. */
  readonly primaryRole = computed<PlayerRole | null>(() => {
    const ending = this.endingType();
    if (ending === null || this.landingConflict()) {
      return null;
    }
    return ending === 'winner' ? 'scoring' : 'losing';
  });
  readonly secondaryExpanded = signal(false);
  readonly showScoringPlayers = computed(
    () => this.primaryRole() !== 'losing' || this.secondaryExpanded(),
  );
  readonly showLosingPlayers = computed(
    () => this.primaryRole() !== 'scoring' || this.secondaryExpanded(),
  );
  /** The folded group's current pick, shown on its toggle so a
   * pre-selected player (singles, or the server on a serve fault) is
   * visible without opening it. */
  readonly secondarySelectedNickname = computed<string | null>(() => {
    const role = this.primaryRole();
    if (role === null) {
      return null;
    }
    const id = role === 'scoring' ? this.selectedLosingRosterEntryId() : this.selectedRosterEntryId();
    return this.participants().find((p) => p.roster_entry_id === id)?.nickname ?? null;
  });

  /** True while the losing pick is the server, filled in by a serve
   * fault rather than tapped — dropped again if the ending type moves
   * away from a serve fault. */
  private readonly losingPickedFromServe = signal(false);

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

    // 035: a hand-picked ending that the new landing contradicts (e.g.
    // 'winner' picked, then the landing moved out of bounds) is cleared
    // back to "never touched", so the auto-fill decides again — never
    // left standing as a pick the server would refuse.
    effect(() => {
      const manual = this.manualEndingType();
      if (manual != null && this.disabledEndingTypes().includes(manual)) {
        // Stay on the half the scorer is looking at: dropping the pick
        // would otherwise send the view back to the automatic half and
        // hide the point that was just placed.
        this.viewOverride.set(untracked(() => this.viewTeam()));
        this.manualEndingType.set(undefined);
      }
    });

    // A serve fault is always the server's own fault: pre-select them as
    // the player at fault. Only fills an empty pick, never replaces one the
    // scorer made, and undoes itself if the ending type moves away again.
    effect(() => {
      const serveFault = this.endingType() === 'serve_fault';
      const server = this.servingRosterEntryId();
      const pool = this.losingPlayers();
      const current = untracked(() => this.selectedLosingRosterEntryId());
      const fromServe = untracked(() => this.losingPickedFromServe());
      if (serveFault && server !== null && pool.some((p) => p.roster_entry_id === server)) {
        if (current === null) {
          this.selectedLosingRosterEntryId.set(server);
          this.losingPickedFromServe.set(true);
        }
      } else if (fromServe) {
        this.losingPickedFromServe.set(false);
        // A singles pool's only player stays picked either way.
        if (current === server && pool.length !== 1) {
          this.selectedLosingRosterEntryId.set(null);
        }
      }
    });

    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      const query = window.matchMedia(COMPACT_VIEW_QUERY);
      this.compactView.set(query.matches);
      const onChange = (event: MediaQueryListEvent) => this.compactView.set(event.matches);
      query.addEventListener('change', onChange);
      inject(DestroyRef).onDestroy(() => query.removeEventListener('change', onChange));
    }
  }

  open(): void {
    this.selectedPoint.set(null);
    this.selectedRosterEntryId.set(null);
    this.selectedLosingRosterEntryId.set(null);
    this.manualEndingType.set(undefined);
    this.magnifierVisible.set(false);
    this.viewOverride.set(null);
    this.secondaryExpanded.set(false);
    this.losingPickedFromServe.set(false);
    // jsdom (unit tests) doesn't implement <dialog> — same guard as
    // ConfirmDialogComponent.
    const nativeDialog = this.dialog().nativeElement;
    if (typeof nativeDialog.showModal === 'function') {
      nativeDialog.showModal();
    }
    // showModal() focuses the first focusable element, which is the
    // cancel-score button in the header, where a stray Enter would undo
    // the point. Start on the court instead.
    // focusVisible: false — the ring is for keyboard users; a scorer who
    // just tapped "+" doesn't need the whole court outlined. Browsers
    // without the option simply ignore it.
    this.courtArea().nativeElement.focus({ preventScroll: true, focusVisible: false } as FocusOptions);
  }

  /** Compact view: show the other half of the court. Never records a
   * point on its own. */
  switchHalf(): void {
    this.viewOverride.set(this.viewTeam() === 'A' ? 'B' : 'A');
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
    if (!this.compactView()) {
      this.selectedPoint.set({ x: 0.5, y: 0.5 });
      return;
    }
    // The half view has no net in the middle: pick the middle of the half
    // that is actually in view.
    this.selectedPoint.set({ x: this.viewTeam() === 'A' ? 0.25 : 0.75, y: 0.5 });
  }

  /** FR-003: re-selecting another player before confirming just replaces
   * the pending choice. */
  pickScoringPlayer(rosterEntryId: string): void {
    this.selectedRosterEntryId.set(rosterEntryId);
  }

  pickLosingPlayer(rosterEntryId: string): void {
    this.selectedLosingRosterEntryId.set(rosterEntryId);
    this.losingPickedFromServe.set(false);
  }

  /** 035: tap a chip to pick it; tap the pressed one again to unselect
   * (an explicit null — see `manualEndingType`). Disabled chips stay
   * focusable (`aria-disabled`, not `disabled`) so their reason can be
   * read out, hence the guard here rather than in the browser. */
  pickEndingType(kind: EndingType): void {
    if (this.disabledEndingTypes().includes(kind)) {
      return;
    }
    this.manualEndingType.set(this.endingType() === kind ? null : kind);
    // A tapped ending type says where to look again (autoViewTeam).
    this.viewOverride.set(null);
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
      endingType: this.endingType(),
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

  private updatePointFromClient(rawClientX: number, rawClientY: number): void {
    const [clientX, clientY] = this.clampToVisibleWindow(rawClientX, rawClientY);
    const rect = this.court().nativeElement.getBoundingClientRect();
    const drawnX = (clientX - rect.left) / rect.width;
    const drawnY = (clientY - rect.top) / rect.height;
    const rotated = this.rotated();
    this.selectedPoint.set({
      x: this.clampToLandingRange(rotated ? 1 - drawnX : drawnX),
      y: this.clampToLandingRange(rotated ? 1 - drawnY : drawnY),
    });
  }

  private updateMagnifierLensPosition(clientX: number, clientY: number): void {
    this.magnifierLensPosition.set({ x: clientX, y: clientY - MAGNIFIER_VERTICAL_OFFSET_PX });
  }

  /** A long-press drag keeps reporting positions after the finger leaves
   * the court window (pointer capture). Keep the point inside what is
   * actually drawn — the window minus the other half's switch strip — so
   * it never ends up somewhere the scorer can't see. */
  private clampToVisibleWindow(clientX: number, clientY: number): [number, number] {
    const area = this.courtArea().nativeElement.getBoundingClientRect();
    if (area.width === 0 || area.height === 0) {
      // Not laid out (e.g. jsdom): nothing to clamp against.
      return [clientX, clientY];
    }
    const geometry = this.courtGeometry();
    const peek = (area.width * geometry.peekWidthPct) / 100;
    const left = area.left + (geometry.peekSide === 'left' ? peek : 0);
    const right = area.right - (geometry.peekSide === 'right' ? peek : 0);
    return [
      Math.min(right, Math.max(left, clientX)),
      Math.min(area.bottom, Math.max(area.top, clientY)),
    ];
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
