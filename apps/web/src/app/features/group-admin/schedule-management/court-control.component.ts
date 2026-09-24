import { IconComponent } from '../../../shared/icon/icon.component';
import {
  Component,
  DestroyRef,
  OnInit,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { isMatchPoint } from '../../../core/match-point';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../../core/realtime/reconnect-refetch.service';
import {
  getScoreSwapPreference,
  setScoreSwapPreference,
} from '../../../core/score-swap-preference';
import { ConfirmDialogComponent } from '../shared/confirm-dialog.component';
import { PendingPoint, PendingPointAction } from '../../shot-placement/pending-point';
import { ScoreTapGuard } from '../../shot-placement/score-tap-guard';
import {
  ShotPlacementConfirmed,
  ShotPlacementPickerComponent,
} from '../../shot-placement/shot-placement-picker.component';
import { ScheduleService } from './schedule.service';
import { CourtScheduleStatus, MatchSummary, Team } from './schedule.models';

/** 管理頁「場地控制」區塊之單一場地操作元件（007 US4）——與公開控制板
 * 完全相同的比分/提前結束業務規則，唯一差異是走管理員 PIN session 驗證
 * 路徑而非 token（research.md #10）。斷線提示/操作限制/重連強制覆蓋
 * （FR-021~025）比照公開控制板同一套規則。 */
@Component({
  selector: 'app-court-control',
  imports: [TranslatePipe, ConfirmDialogComponent, ShotPlacementPickerComponent, IconComponent],
  templateUrl: './court-control.component.html',
  styleUrl: './court-control.component.scss',
})
export class CourtControlComponent implements OnInit {
  readonly groupId = input.required<string>();
  readonly court = input.required<CourtScheduleStatus>();
  readonly changed = output<void>();

  private readonly scheduleService = inject(ScheduleService);
  private readonly realtime = inject(RealtimeService);
  private readonly reconnectRefetch = inject(ReconnectRefetchService);
  private readonly destroyRef = inject(DestroyRef);

  readonly connectionState = this.realtime.connectionState;
  readonly endMatchDialog = viewChild<ConfirmDialogComponent>('endMatchDialog');
  readonly shotPlacementPicker = viewChild<ShotPlacementPickerComponent>('shotPlacementPicker');

  /** 038-freeze-while-picker-open: unlike the public control panel and the
   * scoreboard, this component holds NO live state of its own — every score
   * change arrives only as a brand-new `court` input after the parent
   * refetches the whole schedule. That is fine until the detail picker is
   * open: a match-ending point makes the backend push `match.ended`, the
   * parent refetches, `current_match` comes back null, and the template's
   * `@if` tears the picker's DOM out from under the scorer mid-entry.
   *
   * Freezing on the state captured when "+" was pressed closes that race.
   * It deliberately freezes THIS court block only — `changed.emit()` still
   * fires immediately, so the roster and every other court stay live
   * (constitution III); see AllCourtsCourtBlockComponent's identical field. */
  private readonly frozenCourt = signal<CourtScheduleStatus | null>(null);
  readonly displayCourt = computed<CourtScheduleStatus>(() => this.frozenCourt() ?? this.court());

  // Lets whoever's scoring swap which side each team's block renders on —
  // remembered per court, not globally, since a different physical court
  // may warrant a different left/right arrangement. Read in ngOnInit, not a
  // field initializer — `court` is a required input and only guaranteed set
  // by the time lifecycle hooks run, not necessarily at construction.
  readonly swapped = signal(false);
  readonly leftTeam = computed<Team>(() => (this.swapped() ? 'B' : 'A'));
  readonly rightTeam = computed<Team>(() => (this.swapped() ? 'A' : 'B'));

  // feature/control-panel-scoreboard-style: same pulse-on-genuine-change
  // animation as ScoreboardComponent/ControlPanelComponent. Unlike those,
  // this component has no live-patched local state of its own — every score
  // change (self-inflicted or from another scorer) only ever arrives as a
  // brand-new `court` input once the parent's `changed` output triggers its
  // own refetch — so the comparison happens in the effect below instead of
  // inline at each call site.
  readonly scorePulseA = signal(false);
  readonly scorePulseB = signal(false);
  private readonly pulseTimeouts: Partial<Record<Team, ReturnType<typeof setTimeout>>> = {};
  private lastPulseMatchId: string | null = null;
  private lastPulseScoreA = 0;
  private lastPulseScoreB = 0;

  private subscribedChannel: string | null = null;

  constructor() {
    this.reconnectRefetch
      .onReconnect()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.changed.emit());

    effect(() => {
      // displayCourt(), not court(): the pulse must fire once per change the
      // scorer can actually SEE. Bound to the raw input it would animate an
      // update hidden behind the freeze and then stay still when that update
      // finally becomes visible.
      const match = this.displayCourt().current_match;
      if (!match) {
        this.lastPulseMatchId = null;
        return;
      }
      if (this.lastPulseMatchId === match.match_id) {
        if (match.score_a !== this.lastPulseScoreA) {
          this.triggerScorePulse('A');
        }
        if (match.score_b !== this.lastPulseScoreB) {
          this.triggerScorePulse('B');
        }
      }
      this.lastPulseMatchId = match.match_id;
      this.lastPulseScoreA = match.score_a;
      this.lastPulseScoreB = match.score_b;
    });

    // 場地 court_id 一旦確定（掛載後恆定不變）即訂閱一次頻道；`schedule`
    // 每次重新整理都會建立新的 CourtScheduleStatus 物件，但同一場地的
    // court_id 不變，故只需訂閱一次，不隨每次 changed 事件重複訂閱。
    effect(() => {
      const channel = `court:${this.groupId()}:${this.court().court_id}`;
      if (this.subscribedChannel === channel) {
        return;
      }
      this.subscribedChannel = channel;
      for (const event of [
        'match.scoreUpdated',
        'match.ended',
        'rotation.updated',
        'match.nextRound',
      ]) {
        this.realtime
          .subscribe(channel, event)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe(() => this.changed.emit());
      }
    });
  }

  ngOnInit(): void {
    this.swapped.set(getScoreSwapPreference(this.court().court_id));
  }

  toggleSwap(): void {
    const next = !this.swapped();
    this.swapped.set(next);
    setScoreSwapPreference(this.court().court_id, next);
  }

  /** Restarts the CSS pulse animation on `side`'s score even if it's still
   * mid-animation from a previous change — see ScoreboardComponent's
   * identical method for the full rationale. */
  private triggerScorePulse(side: Team): void {
    const pulseSignal = side === 'A' ? this.scorePulseA : this.scorePulseB;
    clearTimeout(this.pulseTimeouts[side]);
    pulseSignal.set(false);
    requestAnimationFrame(() => {
      pulseSignal.set(true);
      this.pulseTimeouts[side] = setTimeout(() => pulseSignal.set(false), 1200);
    });
  }

  /** feature/control-panel-scoreboard-style: resolves one of the four
   * station slots for `team`'s top/bottom pill — mirrors
   * ControlPanelComponent's identical method (see its comment for why
   * `slot` is a fixed screen position whose left/right court depends on
   * which screen half the team is drawn in). */
  serveRosterId(match: MatchSummary, team: Team, slot: 'top' | 'bottom'): string | null {
    const serve = match.serve;
    if (!serve) {
      return null;
    }
    // Teams face each other across the net, so a team's right-hand court
    // is at the bottom of the screen when it plays from the left, and at
    // the top when it plays from the right.
    const rightCourtSlot = team === this.leftTeam() ? 'bottom' : 'top';
    const takesRightCourt = slot === rightCourtSlot;
    if (team === 'A') {
      return takesRightCourt ? serve.team_a_right_roster_entry_id : serve.team_a_left_roster_entry_id;
    }
    return takesRightCourt ? serve.team_b_right_roster_entry_id : serve.team_b_left_roster_entry_id;
  }

  /** A station pill is a fixed-size chip in a court corner, not a name
   * list — displayName truncates to the first 2 characters so a long
   * nickname never forces the pill (or the court markings around it) to
   * grow or wrap; `nickname` (the untruncated original) is kept alongside
   * it for the pill's aria-label, so screen readers still get the full
   * name even though the visible text doesn't. */
  station(
    match: MatchSummary,
    rosterEntryId: string | null,
  ): { nickname: string; displayName: string; isServer: boolean } | null {
    if (!rosterEntryId) {
      return null;
    }
    const participant = match.participants.find((p) => p.roster_entry_id === rosterEntryId);
    if (!participant) {
      return null;
    }
    return {
      nickname: participant.nickname,
      displayName: participant.nickname.slice(0, 2),
      isServer: match.serve?.server_roster_entry_id === rosterEntryId,
    };
  }

  /** 038: one score request at a time, plus a short cooldown after each —
   * see ScoreTapGuard. Shared by the plain +1/−1 buttons, the detailed-mode
   * "+" and the picker's "cancel score". The other three scoring screens have
   * had this since 032; the admin board never did, so until now a double-tap
   * here could score twice. */
  private readonly scoreGuard = new ScoreTapGuard();

  /** `force` (039): the caller is a deliberate second action — the scorer
   * already confirmed the match-point dialog — not a possible double-tap.
   * hold() locks unconditionally, where tryAcquire() would refuse inside
   * the cooldown left by a previous request and drop the point in silence:
   * the scorer confirms, the match doesn't end, and nothing says why. */
  score(side: Team, delta: 1 | -1, force = false): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-023
    }
    const matchId = this.displayCourt().current_match?.match_id;
    if (!matchId) {
      return;
    }
    if (force) {
      this.scoreGuard.hold();
    } else if (!this.scoreGuard.tryAcquire()) {
      return;
    }
    this.scheduleService
      .scoreMatch(this.groupId(), this.court().court_id, matchId, side, delta)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.scoreGuard.release();
          this.changed.emit();
        },
        error: () => this.scoreGuard.release(),
      });
  }

  /** 039-match-point-confirm: which side the open match-point dialog is
   * confirming for — `confirmed` carries no payload, so the side has to be
   * remembered here. Doubles as the re-entrancy flag (see plusPressed).
   * Cleared by the dialog's `closed` output, which covers Esc too. */
  readonly pendingMatchPointSide = signal<Team | null>(null);
  readonly matchPointDialog = viewChild<ConfirmDialogComponent>('matchPointDialog');

  /** Every "+" goes through here (039). Three ways out:
   *
   *   detailed mode          → the shot-placement picker, unchanged (038)
   *   simple mode + match pt → confirm first; the point is irreversible
   *   otherwise              → score it, unchanged
   *
   * Only simple mode gets the confirmation: detailed mode's picker already
   * offers "cancel this point", which undoes a match-ending point too.
   *
   * Deliberately does NOT take the ScoreTapGuard. tryAcquire() is only
   * undone by release(), and a cancelled dialog has no release point, so
   * grabbing it here would leave this court's scoring locked forever after
   * a single cancel. Scoring takes the guard in score(), as always. */
  plusPressed(side: Team): void {
    if (this.pendingMatchPointSide() !== null) {
      return; // a confirmation is already open — never stack two
    }
    const match = this.displayCourt().current_match;
    if (!match) {
      return;
    }
    if (match.detailed_scoring_enabled) {
      this.scoreThenOpenPicker(side);
      return;
    }
    const own = side === 'A' ? match.score_a : match.score_b;
    const other = side === 'A' ? match.score_b : match.score_a;
    if (!isMatchPoint(own, other, match.target_score, match.cap_score, match.win_by)) {
      this.score(side, 1);
      return;
    }
    this.pendingMatchPointSide.set(side);
    this.matchPointDialog()?.open();
  }

  onMatchPointConfirmed(): void {
    const side = this.pendingMatchPointSide();
    if (side === null) {
      return;
    }
    // force: the scorer just confirmed, so this must not be swallowed by a
    // leftover cooldown. Runs before `closed` clears the side above.
    this.score(side, 1, true);
  }

  /** Bound to the dialog's `closed` output — fires for the confirm button,
   * the cancel button and Esc alike, so the pending side can never be left
   * set (which would wedge plusPressed's re-entrancy check). */
  onMatchPointDialogClosed(): void {
    this.pendingMatchPointSide.set(null);
  }

  /** 038-score-then-record: which side the currently-open picker is recording
   * detail for — set right before open(), bound to the picker's
   * `scoringTeam` input. */
  readonly pendingScoringSide = signal<Team>('A');
  /** Who was serving THIS rally — captured from the match's serve state right
   * BEFORE the point is applied. Not the post-point value: the winner always
   * serves next in badminton, so afterwards it would always equal the scoring
   * side and could never distinguish a side-out from a server holding serve.
   * The picker uses it to stop treating an own-serve win as a serve fault. */
  readonly pendingServingTeam = signal<Team | null>(null);
  /** The serving team's own score before this point, captured alongside
   * `pendingServingTeam` — its parity says which service court the serve had
   * to be delivered to. */
  readonly pendingServingScore = signal<number | null>(null);
  /** Who served this rally, captured alongside `pendingServingTeam` — on a
   * serve fault the picker pre-selects them as the player at fault. */
  readonly pendingServingRosterEntryId = signal<string | null>(null);
  // The point the picker is recording detail for, captured once when "+" is
  // tapped. The handlers below target it rather than re-deriving "the current
  // match" when the scorer eventually acts, since a match-ending point can
  // mean the court has already moved on by then.
  private pendingPoint: PendingPoint | null = null;
  private pickerOpen = false;
  /** 038-cancel-score: surfaced inline on the board when undoMatchCompletion()
   * refuses — the round already advanced, or this court's next match has
   * already been scored. */
  readonly cancelScoreErrorKey = signal<string | null>(null);

  /** Applies the point as a plain +1 — exactly as simple mode does, so the
   * match's pace never waits on the dialog — and opens the picker in the SAME
   * tap, before the request returns. Whatever the scorer does in the picker
   * before the point's score_event_id is known waits in PendingPoint; if the
   * point turns out not to have been applied, the picker closes again. */
  scoreThenOpenPicker(side: Team): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-018
    }
    const current = this.displayCourt();
    const currentMatch = current.current_match;
    if (!currentMatch || !this.scoreGuard.tryAcquire()) {
      return;
    }
    const point = new PendingPoint(currentMatch.match_id, side);
    this.pendingPoint = point;
    this.pendingScoringSide.set(side);
    this.pendingServingTeam.set(currentMatch.serve?.server_team ?? null);
    this.pendingServingRosterEntryId.set(currentMatch.serve?.server_roster_entry_id ?? null);
    this.pendingServingScore.set(
      !currentMatch.serve
        ? null
        : currentMatch.serve.server_team === 'A'
          ? currentMatch.score_a
          : currentMatch.score_b,
    );
    this.cancelScoreErrorKey.set(null);
    this.frozenCourt.set(current);
    this.pickerOpen = true;
    this.shotPlacementPicker()?.open();

    this.scheduleService
      .scoreMatch(this.groupId(), this.court().court_id, point.matchId, side, 1)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.scoreGuard.release();
          if (!result.applied || !result.score_event_id) {
            this.abandonPoint(point);
            this.changed.emit();
            return;
          }
          // Keep the backdrop on this exact patched match while the picker is
          // still up; changed.emit() below still refetches immediately so the
          // roster and every other court stay live.
          if (this.pickerOpen && this.pendingPoint === point) {
            this.frozenCourt.set({
              ...current,
              current_match: {
                ...currentMatch,
                score_a: result.score_a,
                score_b: result.score_b,
                serve: result.serve,
              },
            });
          }
          this.changed.emit();
          const queued = point.resolve(result.score_event_id, result.status !== 'in_progress');
          if (queued) {
            this.runPickerAction(point, queued);
          }
        },
        error: () => {
          this.scoreGuard.release();
          this.abandonPoint(point);
        },
      });
  }

  /** The point never got applied: drop it, and close its picker if the scorer
   * is still in it (FR-017 — never ask for detail on a point that doesn't
   * exist). */
  private abandonPoint(point: PendingPoint): void {
    if (this.pendingPoint !== point) {
      return;
    }
    this.pendingPoint = null;
    if (this.pickerOpen) {
      this.shotPlacementPicker()?.skip();
    }
    this.pickerOpen = false;
    this.frozenCourt.set(null);
  }

  /** Bound to the picker's `(closed)` output, which fires however the dialog
   * closed (confirm/skip/cancel) — the single place the freeze lifts. */
  onShotPlacementClosed(): void {
    this.pickerOpen = false;
    this.frozenCourt.set(null);
  }

  onShotPlacementConfirmed(detail: ShotPlacementConfirmed): void {
    this.requestPickerAction({ kind: 'confirm', detail });
  }

  /** 038-cancel-score: the scorer decided the point itself shouldn't have been
   * awarded (the wrong team's "+" got pressed) — undoes it. */
  onShotPlacementCancelled(): void {
    this.requestPickerAction({ kind: 'cancel' });
  }

  private requestPickerAction(action: PendingPointAction): void {
    const point = this.pendingPoint;
    if (point && point.request(action)) {
      this.runPickerAction(point, action);
    }
  }

  private runPickerAction(point: PendingPoint, action: PendingPointAction): void {
    const scoreEventId = point.scoreEventId;
    if (this.connectionState() !== 'connected' || scoreEventId === null) {
      return;
    }
    if (action.kind === 'confirm') {
      this.scheduleService
        .recordShotPlacement(
          this.groupId(),
          this.court().court_id,
          point.matchId,
          scoreEventId,
          action.detail.rosterEntryId,
          action.detail.losingRosterEntryId,
          action.detail.landingX,
          action.detail.landingY,
          action.detail.endingType,
        )
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => {
          // The point itself already stands whatever happens here (FR-016) —
          // a failed attach never rolls the score back.
          this.clearPendingPoint(point);
          this.changed.emit();
        });
      return;
    }

    this.cancelScoreErrorKey.set(null);
    // A point that just completed the match needs undoMatchCompletion()
    // rather than the plain -1 the "-1" button sends: the match's completion
    // (and its MatchResult) has to come undone too, not just the score.
    if (point.matchCompleted) {
      this.scheduleService
        .undoMatchCompletion(this.groupId(), this.court().court_id, point.matchId, point.side)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: () => {
            this.clearPendingPoint(point);
            this.changed.emit();
          },
          error: (error: ApiError) => {
            this.clearPendingPoint(point);
            this.cancelScoreErrorKey.set(error.i18nKey);
          },
        });
      return;
    }

    // hold(), not tryAcquire(): the cooldown from the "+" that opened this
    // picker may still be running, and this correction must not be dropped.
    this.scoreGuard.hold();
    this.scheduleService
      .scoreMatch(this.groupId(), this.court().court_id, point.matchId, point.side, -1)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.scoreGuard.release();
          this.clearPendingPoint(point);
          this.changed.emit();
        },
        error: () => this.scoreGuard.release(),
      });
  }

  private clearPendingPoint(point: PendingPoint): void {
    if (this.pendingPoint === point) {
      this.pendingPoint = null;
    }
  }

  openEndMatchDialog(): void {
    this.endMatchDialog()?.open();
  }

  confirmEndMatch(): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-023
    }
    const matchId = this.displayCourt().current_match?.match_id;
    if (!matchId) {
      return;
    }
    this.scheduleService
      .endMatch(this.groupId(), this.court().court_id, matchId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.changed.emit());
  }
}
