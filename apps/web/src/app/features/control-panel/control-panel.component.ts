import { Component, DestroyRef, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../core/api/api-error';
import { CourtControlService } from '../../core/api/court-control.service';
import { CourtByTokenResponse } from '../../core/api/court-link.models';
import { CourtStateResponse, Team } from '../../core/api/court-live-state.models';
import { LinkHeartbeatService } from '../../core/api/link-heartbeat.service';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../core/realtime/reconnect-refetch.service';
import { getScoreSwapPreference, setScoreSwapPreference } from '../../core/score-swap-preference';
import { ConfirmDialogComponent } from '../group-admin/shared/confirm-dialog.component';
import { LanguageSwitcherComponent } from '../../core/language/language-switcher.component';
import {
  ShotPlacementConfirmed,
  ShotPlacementPickerComponent,
} from '../shot-placement/shot-placement-picker.component';

/** 單一場地控制板：連結初始化/心跳（T042）+ link.regenerated 專屬失效
 * 提示（T041，FR-035）+ +1/-1／提前結束操作與即時狀態顯示（007
 * US1/US2）。 */
@Component({
  selector: 'app-control-panel',
  imports: [TranslatePipe, ConfirmDialogComponent, LanguageSwitcherComponent, ShotPlacementPickerComponent],
  templateUrl: './control-panel.component.html',
  styleUrl: './control-panel.component.scss',
})
export class ControlPanelComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly heartbeat = inject(LinkHeartbeatService);
  private readonly realtime = inject(RealtimeService);
  private readonly courtControl = inject(CourtControlService);
  private readonly reconnectRefetch = inject(ReconnectRefetchService);
  private readonly destroyRef = inject(DestroyRef);

  private readonly token = this.route.snapshot.paramMap.get('courtToken')!;
  private subscribedChannel: string | null = null;

  readonly courtInfo = signal<CourtByTokenResponse | null>(null);
  readonly liveState = signal<CourtStateResponse | null>(null);
  readonly linkInvalidated = signal(false);
  readonly loading = signal(true);
  readonly errorKey = signal<string | null>(null);

  /** 032-freeze-while-picker-open: see ScoreboardComponent's identical
   * field for the full rationale — a match-ending point's realtime
   * match.ended/next-round push must not swap out `current_match` (and so
   * destroy the still-open picker's DOM) before the scorer can respond. */
  private readonly frozenState = signal<CourtStateResponse | null>(null);
  readonly displayState = computed(() => this.frozenState() ?? this.liveState());

  readonly connectionState = this.realtime.connectionState;

  readonly endMatchDialog = viewChild<ConfirmDialogComponent>('endMatchDialog');
  readonly shotPlacementPicker = viewChild<ShotPlacementPickerComponent>('shotPlacementPicker');

  // Lets whoever's scoring swap which side each team's block renders on —
  // remembered per court (`this.token`), not globally, since a different
  // physical court may warrant a different left/right arrangement.
  readonly swapped = signal(getScoreSwapPreference(this.token));
  readonly leftTeam = computed<Team>(() => (this.swapped() ? 'B' : 'A'));
  readonly rightTeam = computed<Team>(() => (this.swapped() ? 'A' : 'B'));

  constructor() {
    // FR-024: 重新連線後強制拉取最新完整狀態覆蓋本地暫存，不信任斷線
    // 期間可能累積的本地分數。
    this.reconnectRefetch
      .onReconnect()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadState());

    this.heartbeat
      .watchCourtLink(this.token)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (info) => {
          if (this.linkInvalidated()) {
            return; // stale connection's link already superseded — ignore
          }
          this.courtInfo.set(info);
          this.loading.set(false);
          if (!this.subscribedChannel) {
            this.subscribeToLiveEvents(info);
            this.loadState();
          }
        },
        error: (error: ApiError) => {
          if (this.linkInvalidated()) {
            return;
          }
          this.loading.set(false);
          this.errorKey.set(error.i18nKey);
        },
      });
  }

  private loadState(): void {
    this.courtControl
      .getState(this.token)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((state) => this.liveState.set(state));
  }

  private subscribeToLiveEvents(info: CourtByTokenResponse): void {
    this.subscribedChannel = `court:${info.group_id}:${info.court_id}`;

    this.realtime
      .subscribe(this.subscribedChannel, 'link.regenerated')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((message) => {
        const data = message.data as { link_type: string };
        if (data.link_type === 'control_panel') {
          this.linkInvalidated.set(true);
        }
      });

    this.realtime
      .subscribe(this.subscribedChannel, 'match.scoreUpdated')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((message) => {
        const data = message.data as { match_id: string; score_a: number; score_b: number };
        const state = this.liveState();
        if (state?.current_match?.match_id === data.match_id) {
          this.liveState.set({
            ...state,
            current_match: { ...state.current_match, score_a: data.score_a, score_b: data.score_b },
          });
        }
      });

    this.realtime
      .subscribe(this.subscribedChannel, 'match.ended')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadState());

    this.realtime
      .subscribe(this.subscribedChannel, 'rotation.updated')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadState());

    this.realtime
      .subscribe(this.subscribedChannel, 'match.nextRound')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadState());
  }

  score(side: Team, delta: 1 | -1): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-023: 離線期間不允許操作
    }
    const matchId = this.liveState()?.current_match?.match_id;
    if (!matchId) {
      return;
    }
    this.courtControl
      .score(this.token, matchId, side, delta)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((result) => {
        const state = this.liveState();
        if (state?.current_match?.match_id === result.match_id && result.status === 'in_progress') {
          this.liveState.set({
            ...state,
            current_match: {
              ...state.current_match,
              score_a: result.score_a,
              score_b: result.score_b,
            },
          });
        }
      });
  }

  /** 032-score-then-record: which side the currently-open picker is
   * recording detail for — set right before open() below, bound to the
   * picker's `scoringTeam` input in the template. */
  readonly pendingScoringSide = signal<Team>('A');
  // Captured once, right when the point is scored — onShotPlacementConfirmed()
  // and onShotPlacementCancelled() below use these rather than re-deriving
  // "the current match" from liveState()/frozenState() at the time the
  // scorer eventually acts, since a match-ending point can mean the court
  // has already moved on to a different match by then.
  private pendingMatchId: string | null = null;
  private pendingScoreEventId: string | null = null;
  // 032-cancel-score: whether the point that opened the picker was the
  // match-DECIDING one (result.status !== 'in_progress') — onShotPlacementCancelled()
  // below needs undoMatchCompletion() instead of the plain -1 for that point.
  private pendingMatchCompleted = false;
  // Surfaced inline (not the full-page errorKey() above) when
  // undoMatchCompletion() refuses — round already advanced, or the next
  // match on this court already got scored.
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
   * same "+1" does. Freezing only once the response arrives (inside the
   * subscribe below) is too late to protect against that: the earlier
   * match.ended-triggered loadState() would have already blanked
   * liveState().current_match, which would in turn make the @if hosting
   * the picker false and shotPlacementPicker() undefined by the time
   * open() below ever runs — the picker would never even appear. Freezing
   * on the state captured HERE, before the request is even sent, closes
   * that race: nothing that arrives afterward can matter until this
   * component itself lifts the freeze. */
  scoreThenOpenPicker(side: Team): void {
    if (this.connectionState() !== 'connected') {
      return;
    }
    const state = this.liveState();
    const currentMatch = state?.current_match;
    if (!state || !currentMatch) {
      return;
    }
    const matchId = currentMatch.match_id;
    this.frozenState.set(state);

    this.courtControl
      .score(this.token, matchId, side, 1)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          if (!result.applied) {
            this.frozenState.set(null); // nothing to protect — release right away
            return;
          }
          const patched: CourtStateResponse = {
            ...state,
            current_match: {
              ...currentMatch,
              score_a: result.score_a,
              score_b: result.score_b,
            },
          };
          // For a plain continuing point also commit the patch to the real
          // liveState() so the score is still correct once the freeze
          // lifts; for the match-ending point, leave liveState() alone —
          // whatever match.ended/next-round pushes already arrived (or
          // still will) replace it wholesale.
          this.frozenState.set(patched);
          if (result.status === 'in_progress') {
            this.liveState.set(patched);
          }
          if (result.score_event_id) {
            this.pendingMatchId = matchId;
            this.pendingScoreEventId = result.score_event_id;
            this.pendingScoringSide.set(side);
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
      .recordShotPlacement(
        this.token,
        matchId,
        scoreEventId,
        event.rosterEntryId,
        event.losingRosterEntryId,
        event.landingX,
        event.landingY,
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.pendingMatchId = null;
        this.pendingScoreEventId = null;
      });
  }

  /** 032-cancel-score: the scorer decided the point itself shouldn't have
   * been awarded (e.g. the wrong team's "+" was pressed) — undoes it. A
   * point that just completed the match needs undoMatchCompletion() instead
   * of the plain -1 the control panel's own "-1" button uses: see
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
        .undoMatchCompletion(this.token, matchId, side)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: () => {
            this.pendingMatchId = null;
            this.pendingScoreEventId = null;
            this.pendingMatchCompleted = false;
            this.loadState();
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
      .score(this.token, matchId, side, -1)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((result) => {
        this.pendingMatchId = null;
        this.pendingScoreEventId = null;
        const state = this.liveState();
        if (state?.current_match?.match_id === result.match_id && result.status === 'in_progress') {
          this.liveState.set({
            ...state,
            current_match: {
              ...state.current_match,
              score_a: result.score_a,
              score_b: result.score_b,
            },
          });
        }
      });
  }

  openEndMatchDialog(): void {
    this.endMatchDialog()?.open();
  }

  confirmEndMatch(): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-023: 離線期間不允許操作
    }
    const matchId = this.liveState()?.current_match?.match_id;
    if (!matchId) {
      return;
    }
    this.courtControl
      .endMatch(this.token, matchId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadState());
  }

  toggleSwap(): void {
    const next = !this.swapped();
    this.swapped.set(next);
    setScoreSwapPreference(this.token, next);
  }
}
