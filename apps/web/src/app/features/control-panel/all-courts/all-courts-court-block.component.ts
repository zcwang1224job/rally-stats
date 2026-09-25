import { IconComponent } from '../../../shared/icon/icon.component';
import {
  Component,
  DestroyRef,
  OnInit,
  computed,
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
import { waitingReasonKey } from '../../../core/waiting-reason-label';
import { CourtControlService } from '../../../core/api/court-control.service';
import { CourtLiveState, Team } from '../../../core/api/court-live-state.models';
import { RealtimeService } from '../../../core/realtime/ably.service';
import {
  getScoreSwapPreference,
  setScoreSwapPreference,
} from '../../../core/score-swap-preference';
import { ConfirmDialogComponent } from '../../group-admin/shared/confirm-dialog.component';
import { PendingPoint, PendingPointAction } from '../../shot-placement/pending-point';
import { ScoreTapGuard } from '../../shot-placement/score-tap-guard';
import {
  ShotPlacementConfirmed,
  ShotPlacementPickerComponent,
} from '../../shot-placement/shot-placement-picker.component';

/** 全部場地控制板中單一場地的操作區塊（007 US5）——每個場地一個獨立
 * 元件實例，版面天然區隔避免誤按（FR-001），且各自的確認彈窗
 * viewChild 不會互相衝突（比照管理頁 court-control 元件的設計）。與單一
 * 場地控制板/管理頁完全相同的業務規則，僅差在走全部場地 token 這組
 * 端點。 */
@Component({
  selector: 'app-all-courts-court-block',
  imports: [TranslatePipe, ConfirmDialogComponent, ShotPlacementPickerComponent, IconComponent],
  templateUrl: './all-courts-court-block.component.html',
  styleUrl: './all-courts-court-block.component.scss',
})
export class AllCourtsCourtBlockComponent implements OnInit {
  readonly waitingReasonKey = waitingReasonKey;
  readonly token = input.required<string>();
  readonly courtId = input.required<string>();
  readonly name = input.required<string>();
  readonly state = input.required<CourtLiveState | null>();
  /** 043: every court block gets the group id; this one subscribes by
   * itself and has no use for it. */
  readonly groupId = input<string | null>(null);
  readonly changed = output<void>();

  private readonly courtControl = inject(CourtControlService);
  private readonly realtime = inject(RealtimeService);
  private readonly destroyRef = inject(DestroyRef);

  readonly connectionState = this.realtime.connectionState;
  readonly endMatchDialog = viewChild<ConfirmDialogComponent>('endMatchDialog');
  readonly shotPlacementPicker = viewChild<ShotPlacementPickerComponent>('shotPlacementPicker');

  /** 032-freeze-while-picker-open: see ScoreboardComponent's identical
   * field for the full rationale — the parent's `changed.emit()`-driven
   * refetch (below) still runs immediately so every OTHER court's block
   * stays live, but THIS block ignores the resulting `state` input update
   * while its own picker is open, so a match-ending point can't swap
   * `current_match` out from under it and destroy the picker's DOM. */
  private readonly frozenState = signal<CourtLiveState | null>(null);
  readonly displayState = computed(() => this.frozenState() ?? this.state());

  // Lets whoever's scoring swap which side each team's block renders on —
  // remembered per court, not globally, since a different physical court
  // may warrant a different left/right arrangement. Read in ngOnInit, not a
  // field initializer — `courtId` is a required input and only guaranteed
  // set by the time lifecycle hooks run, not necessarily at construction.
  readonly swapped = signal(false);
  readonly leftTeam = computed<Team>(() => (this.swapped() ? 'B' : 'A'));
  readonly rightTeam = computed<Team>(() => (this.swapped() ? 'A' : 'B'));

  ngOnInit(): void {
    this.swapped.set(getScoreSwapPreference(this.courtId()));
  }

  toggleSwap(): void {
    const next = !this.swapped();
    this.swapped.set(next);
    setScoreSwapPreference(this.courtId(), next);
  }

  /** One score request at a time, plus a short cooldown after each one —
   * see ScoreTapGuard. Shared by the plain +1/−1 buttons, the detailed-mode
   * "+" and the picker's "cancel score". */
  private readonly scoreGuard = new ScoreTapGuard();

  /** 039-match-point-confirm: which side the open match-point dialog is
   * confirming for; doubles as the re-entrancy flag. Cleared by the
   * dialog's `closed` output, which covers Esc too. */
  readonly pendingMatchPointSide = signal<Team | null>(null);
  readonly matchPointDialog = viewChild<ConfirmDialogComponent>('matchPointDialog');

  /** Every "+" goes through here (039) — see CourtControlComponent's
   * identical method for why the ScoreTapGuard is deliberately not taken
   * here and why the re-entrancy check doesn't rely on the dialog's
   * modality. Reads displayState() so a frozen board still judges on the
   * score the scorer can actually see. */
  plusPressed(side: Team): void {
    if (this.pendingMatchPointSide() !== null) {
      return;
    }
    const match = this.displayState()?.current_match;
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
    this.score(side, 1, true);
  }

  onMatchPointDialogClosed(): void {
    this.pendingMatchPointSide.set(null);
  }

  /** `force` (039): the confirmed match-point dialog is a deliberate second
   * decision, not a possible double-tap, so it must not be dropped by a
   * leftover cooldown. See CourtControlComponent.score(). */
  score(side: Team, delta: 1 | -1, force = false): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-023
    }
    const matchId = this.state()?.current_match?.match_id;
    if (!matchId) {
      return;
    }
    if (force) {
      this.scoreGuard.hold();
    } else if (!this.scoreGuard.tryAcquire()) {
      return;
    }
    this.courtControl
      .scoreAllCourts(this.token(), this.courtId(), matchId, side, delta)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.scoreGuard.release();
          this.changed.emit();
        },
        error: () => this.scoreGuard.release(),
      });
  }

  /** 032-score-then-record: which side the currently-open picker is
   * recording detail for — set right before open() below, bound to the
   * picker's `scoringTeam` input in the template. */
  readonly pendingScoringSide = signal<Team>('A');
  /** Who was serving THIS rally — captured from `currentMatch.serve` right
   * BEFORE the point below is applied (not the response's post-point
   * value, which always equals `side`: the winner always serves next in
   * badminton, so it could never distinguish a side-out from a server who
   * just won their own rally). Bound to the picker's `servingTeam` input,
   * which uses it to stop treating an own-serve win as a possible "serve
   * fault". */
  readonly pendingServingTeam = signal<Team | null>(null);
  /** The serving team's own score before this point, captured with
   * `pendingServingTeam` — the picker's `servingScore` input, whose
   * parity says which service court was the serve's legal target. */
  readonly pendingServingScore = signal<number | null>(null);
  /** The player who served this rally, captured with
   * `pendingServingTeam` — the picker pre-selects them as the player
   * at fault on a serve fault. */
  readonly pendingServingRosterEntryId = signal<string | null>(null);
  // The point the picker is recording detail for — captured once, right
  // when "+" is tapped: onShotPlacementConfirmed()/onShotPlacementCancelled()
  // below target it rather than re-deriving "the current match" from
  // state()/displayState() when the scorer eventually acts, since a
  // match-ending point can mean the court has already moved on to a
  // different match by then.
  private pendingPoint: PendingPoint | null = null;
  private pickerOpen = false;
  // Surfaced inline when undoMatchCompletionAllCourts() refuses — round
  // already advanced, or the next match on this court already got scored.
  readonly cancelScoreErrorKey = signal<string | null>(null);

  /** Applies the point (a plain +1, same as simple mode — match pace never
   * waits on the detail dialog below) and opens the shared picker in the
   * SAME tap, before the request returns — see ScoreboardComponent's
   * identical method for the full rationale.
   *
   * 032-freeze-while-picker-open: the parent (all-courts-control-panel)
   * refetches ALL courts on a match.ended push, which would update this
   * block's `state` input while the picker is up — making @if's condition
   * false and tearing the picker down. Freezing on the state captured
   * HERE, before the request is even sent, closes that race. */
  scoreThenOpenPicker(side: Team): void {
    if (this.connectionState() !== 'connected') {
      return;
    }
    const current = this.state();
    const currentMatch = current?.current_match;
    if (!current || !currentMatch || !this.scoreGuard.tryAcquire()) {
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
    this.frozenState.set(current);
    this.pickerOpen = true;
    this.shotPlacementPicker()?.open();

    this.courtControl
      .scoreAllCourts(this.token(), this.courtId(), point.matchId, side, 1)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.scoreGuard.release();
          if (!result.applied || !result.score_event_id) {
            this.abandonPoint(point);
            this.changed.emit();
            return;
          }
          // Keep the backdrop on this exact patched match/score while the
          // picker is still up — changed.emit() below still refetches
          // immediately for every other court.
          if (this.pickerOpen && this.pendingPoint === point) {
            this.frozenState.set({
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

  /** The point never got applied: drop it, and close its picker if the
   * scorer is still in it. */
  private abandonPoint(point: PendingPoint): void {
    if (this.pendingPoint !== point) {
      return;
    }
    this.pendingPoint = null;
    if (this.pickerOpen) {
      this.shotPlacementPicker()?.skip();
    }
    this.pickerOpen = false;
    this.frozenState.set(null);
  }

  /** Bound to the picker's `(closed)` output — see ScoreboardComponent's
   * identical method for the full rationale. */
  onShotPlacementClosed(): void {
    this.pickerOpen = false;
    this.frozenState.set(null);
  }

  onShotPlacementConfirmed(detail: ShotPlacementConfirmed): void {
    this.requestPickerAction({ kind: 'confirm', detail });
  }

  /** 032-cancel-score: the scorer decided the point itself shouldn't have
   * been awarded (e.g. the wrong team's "+" was pressed) — undoes it. */
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
      this.courtControl
        .recordShotPlacementAllCourts(
          this.token(),
          this.courtId(),
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
          this.clearPendingPoint(point);
          this.changed.emit();
        });
      return;
    }

    this.cancelScoreErrorKey.set(null);
    // A point that just completed the match needs
    // undoMatchCompletionAllCourts() instead of the plain -1 this block's
    // own "-1" button uses: see ScoreboardComponent's identical method for
    // the full rationale.
    if (point.matchCompleted) {
      this.courtControl
        .undoMatchCompletionAllCourts(this.token(), this.courtId(), point.matchId, point.side)
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

    this.scoreGuard.hold();
    this.courtControl
      .scoreAllCourts(this.token(), this.courtId(), point.matchId, point.side, -1)
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
    const matchId = this.state()?.current_match?.match_id;
    if (!matchId) {
      return;
    }
    this.courtControl
      .endMatchAllCourts(this.token(), this.courtId(), matchId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.changed.emit());
  }
}
