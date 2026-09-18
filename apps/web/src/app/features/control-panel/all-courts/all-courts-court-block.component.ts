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
import { CourtControlService } from '../../../core/api/court-control.service';
import { CourtLiveState, Team } from '../../../core/api/court-live-state.models';
import { RealtimeService } from '../../../core/realtime/ably.service';
import {
  getScoreSwapPreference,
  setScoreSwapPreference,
} from '../../../core/score-swap-preference';
import { ConfirmDialogComponent } from '../../group-admin/shared/confirm-dialog.component';
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
  imports: [TranslatePipe, ConfirmDialogComponent, ShotPlacementPickerComponent],
  templateUrl: './all-courts-court-block.component.html',
  styleUrl: './all-courts-court-block.component.scss',
})
export class AllCourtsCourtBlockComponent implements OnInit {
  readonly token = input.required<string>();
  readonly courtId = input.required<string>();
  readonly name = input.required<string>();
  readonly state = input.required<CourtLiveState | null>();
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

  score(side: Team, delta: 1 | -1): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-023
    }
    const matchId = this.state()?.current_match?.match_id;
    if (!matchId) {
      return;
    }
    this.courtControl
      .scoreAllCourts(this.token(), this.courtId(), matchId, side, delta)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.changed.emit());
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
  // Captured once, right when the point is scored — onShotPlacementConfirmed()
  // and onShotPlacementCancelled() below use these rather than re-deriving
  // "the current match" from state()/displayState() at the time the scorer
  // eventually acts, since a match-ending point can mean the court has
  // already moved on to a different match by then.
  private pendingMatchId: string | null = null;
  private pendingScoreEventId: string | null = null;
  // 032-cancel-score: whether the point that opened the picker was the
  // match-DECIDING one (result.status !== 'in_progress') — onShotPlacementCancelled()
  // below needs undoMatchCompletionAllCourts() instead of the plain -1 for
  // that point.
  private pendingMatchCompleted = false;
  // Surfaced inline when undoMatchCompletionAllCourts() refuses — round
  // already advanced, or the next match on this court already got scored.
  readonly cancelScoreErrorKey = signal<string | null>(null);

  /** Applies the point immediately (a plain +1, same as simple mode — match
   * pace never waits on the detail dialog below), then opens the shared
   * picker to record supplementary detail (landing spot, exact players)
   * for that already-scored point, pinned to its score_event_id.
   *
   * 032-freeze-while-picker-open: the backend PUBLISHES match.ended (over
   * the realtime websocket) synchronously, from inside the very same
   * request this method's own HTTP call is waiting on — so that push can,
   * and often does, reach this client BEFORE the HTTP response for this
   * same "+1" does. The parent (all-courts-control-panel) subscribes to
   * that push directly and refetches ALL courts on it, which would update
   * this block's `state` input before the response below even arrives if
   * freezing waited until then — making @if's condition false and
   * shotPlacementPicker() undefined by the time open() runs, so the picker
   * would never even appear. Freezing on the state captured HERE, before
   * the request is even sent, closes that race. */
  scoreThenOpenPicker(side: Team): void {
    if (this.connectionState() !== 'connected') {
      return;
    }
    const current = this.state();
    const currentMatch = current?.current_match;
    if (!current || !currentMatch) {
      return;
    }
    const matchId = currentMatch.match_id;
    this.frozenState.set(current);

    this.courtControl
      .scoreAllCourts(this.token(), this.courtId(), matchId, side, 1)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          if (!result.applied) {
            this.frozenState.set(null); // nothing to protect — release right away
            this.changed.emit();
            return;
          }
          // Freeze the backdrop on this exact patched match/score while the
          // picker is open — changed.emit() below still refetches
          // immediately for every other court.
          this.frozenState.set({
            ...current,
            current_match: {
              ...currentMatch,
              score_a: result.score_a,
              score_b: result.score_b,
              serve: result.serve,
            },
          });
          this.changed.emit();
          if (result.score_event_id) {
            this.pendingMatchId = matchId;
            this.pendingScoreEventId = result.score_event_id;
            this.pendingScoringSide.set(side);
            this.pendingServingTeam.set(currentMatch.serve?.server_team ?? null);
            this.pendingServingScore.set(
              !currentMatch.serve
                ? null
                : currentMatch.serve.server_team === 'A'
                  ? currentMatch.score_a
                  : currentMatch.score_b,
            );
            this.pendingMatchCompleted = result.status !== 'in_progress';
            this.cancelScoreErrorKey.set(null);
            this.shotPlacementPicker()?.open();
          } else {
            this.frozenState.set(null);
          }
        },
        error: () => this.frozenState.set(null),
      });
  }

  /** Bound to the picker's `(closed)` output — see ScoreboardComponent's
   * identical method for the full rationale. */
  onShotPlacementClosed(): void {
    this.frozenState.set(null);
  }

  onShotPlacementConfirmed(event: ShotPlacementConfirmed): void {
    const matchId = this.pendingMatchId;
    const scoreEventId = this.pendingScoreEventId;
    if (this.connectionState() !== 'connected' || !matchId || !scoreEventId) {
      return;
    }
    this.courtControl
      .recordShotPlacementAllCourts(
        this.token(),
        this.courtId(),
        matchId,
        scoreEventId,
        event.rosterEntryId,
        event.losingRosterEntryId,
        event.landingX,
        event.landingY,
        event.endingType,
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.pendingMatchId = null;
        this.pendingScoreEventId = null;
        this.changed.emit();
      });
  }

  /** 032-cancel-score: the scorer decided the point itself shouldn't have
   * been awarded (e.g. the wrong team's "+" was pressed) — undoes it. A
   * point that just completed the match needs undoMatchCompletionAllCourts()
   * instead of the plain -1 this block's own "-1" button uses: see
   * ScoreboardComponent's identical method for the full rationale. */
  onShotPlacementCancelled(): void {
    const matchId = this.pendingMatchId;
    if (this.connectionState() !== 'connected' || !matchId) {
      return;
    }
    const side = this.pendingScoringSide();
    this.cancelScoreErrorKey.set(null);

    if (this.pendingMatchCompleted) {
      this.courtControl
        .undoMatchCompletionAllCourts(this.token(), this.courtId(), matchId, side)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: () => {
            this.pendingMatchId = null;
            this.pendingScoreEventId = null;
            this.pendingMatchCompleted = false;
            this.changed.emit();
          },
          error: (error: ApiError) => {
            this.pendingMatchId = null;
            this.pendingScoreEventId = null;
            this.pendingMatchCompleted = false;
            this.cancelScoreErrorKey.set(error.i18nKey);
          },
        });
      return;
    }

    this.courtControl
      .scoreAllCourts(this.token(), this.courtId(), matchId, side, -1)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.pendingMatchId = null;
        this.pendingScoreEventId = null;
        this.changed.emit();
      });
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
