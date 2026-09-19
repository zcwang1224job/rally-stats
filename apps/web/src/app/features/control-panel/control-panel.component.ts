import { Component, DestroyRef, computed, inject, signal, viewChild } from '@angular/core';
import { IconComponent } from '../../shared/icon/icon.component';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../core/api/api-error';
import { CourtControlService } from '../../core/api/court-control.service';
import { CourtByTokenResponse } from '../../core/api/court-link.models';
import {
  CourtStateResponse,
  MatchLiveDetail,
  ScoreMutationResult,
  Team,
} from '../../core/api/court-live-state.models';
import { LinkHeartbeatService } from '../../core/api/link-heartbeat.service';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../core/realtime/reconnect-refetch.service';
import { getScoreSwapPreference, setScoreSwapPreference } from '../../core/score-swap-preference';
import { ConfirmDialogComponent } from '../group-admin/shared/confirm-dialog.component';
import { PendingPoint, PendingPointAction } from '../shot-placement/pending-point';
import { ScoreTapGuard } from '../shot-placement/score-tap-guard';
import {
  ShotPlacementConfirmed,
  ShotPlacementPickerComponent,
} from '../shot-placement/shot-placement-picker.component';

/** 單一場地控制板：連結初始化/心跳（T042）+ link.regenerated 專屬失效
 * 提示（T041，FR-035）+ +1/-1／提前結束操作與即時狀態顯示（007
 * US1/US2）。 */
@Component({
  selector: 'app-control-panel',
  imports: [TranslatePipe, ConfirmDialogComponent, ShotPlacementPickerComponent, IconComponent],
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

  // feature/control-panel-scoreboard-style: same "pop" animation on a
  // genuine score change as ScoreboardComponent — see its identical field
  // for the full rationale. Keyed on the actual A/B side (not the visual
  // left/right slot, which can be swapped) since score_a/score_b are
  // always A/B regardless of which slot currently shows them.
  readonly scorePulseA = signal(false);
  readonly scorePulseB = signal(false);
  private readonly pulseTimeouts: Partial<Record<Team, ReturnType<typeof setTimeout>>> = {};

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
        const data = message.data as {
          match_id: string;
          score_a: number;
          score_b: number;
          serve: MatchLiveDetail['serve'];
        };
        const state = this.liveState();
        if (state?.current_match?.match_id === data.match_id) {
          if (data.score_a !== state.current_match.score_a) {
            this.triggerScorePulse('A');
          }
          if (data.score_b !== state.current_match.score_b) {
            this.triggerScorePulse('B');
          }
          this.liveState.set({
            ...state,
            current_match: {
              ...state.current_match,
              score_a: data.score_a,
              score_b: data.score_b,
              serve: data.serve,
            },
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

  /** feature/control-panel-scoreboard-style: resolves one of the four
   * station slots for `team`'s top/bottom pill. `slot` names a fixed
   * SCREEN position (the block's top edge vs. bottom edge), not a
   * badminton-sense left/right court — teams face each other across the
   * net, so team A's own right service court and team B's own right
   * service court sit on OPPOSITE physical sidelines (see
   * ScoreboardComponent.html's identical comment): binding `_right` to
   * the bottom slot for A but to the TOP slot for B (and vice versa) is
   * what keeps a station's left/right consistent with the real court.
   * This mapping is per-TEAM, not per-screen-half — control-panel
   * additionally lets the scorer swap which half each team renders in
   * (`leftTeam()`/`rightTeam()`), but swapping only moves a team
   * sideways, it never changes which direction that team actually
   * faces, so the top/bottom mirroring must follow the team, not the
   * slot it's currently drawn in. */
  serveRosterId(match: MatchLiveDetail, team: Team, slot: 'top' | 'bottom'): string | null {
    const serve = match.serve;
    if (!serve) {
      return null;
    }
    if (team === 'A') {
      return slot === 'top'
        ? serve.team_a_left_roster_entry_id
        : serve.team_a_right_roster_entry_id;
    }
    return slot === 'top'
      ? serve.team_b_right_roster_entry_id
      : serve.team_b_left_roster_entry_id;
  }

  /** A station pill is a fixed-size chip in a court corner, not a name
   * list — displayName truncates to the first 2 characters so a long
   * nickname never forces the pill (or the court markings around it) to
   * grow or wrap; `nickname` (the untruncated original) is kept alongside
   * it for the pill's aria-label, so screen readers still get the full
   * name even though the visible text doesn't. */
  station(
    match: MatchLiveDetail,
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

  /** One score request at a time, plus a short cooldown after each one —
   * see ScoreTapGuard. Shared by the plain +1/−1 buttons, the detailed-mode
   * "+" and the picker's "cancel score". */
  private readonly scoreGuard = new ScoreTapGuard();

  score(side: Team, delta: 1 | -1): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-023: 離線期間不允許操作
    }
    const matchId = this.liveState()?.current_match?.match_id;
    if (!matchId || !this.scoreGuard.tryAcquire()) {
      return;
    }
    this.courtControl
      .score(this.token, matchId, side, delta)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.scoreGuard.release();
          this.patchLiveScore(side, result);
        },
        error: () => this.scoreGuard.release(),
      });
  }

  private patchLiveScore(side: Team, result: ScoreMutationResult): void {
    const state = this.liveState();
    if (state?.current_match?.match_id === result.match_id && result.status === 'in_progress') {
      this.triggerScorePulse(side);
      this.liveState.set({
        ...state,
        current_match: {
          ...state.current_match,
          score_a: result.score_a,
          score_b: result.score_b,
          serve: result.serve,
        },
      });
    }
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
  // liveState()/frozenState() when the scorer eventually acts, since a
  // match-ending point can mean the court has already moved on to a
  // different match by then.
  private pendingPoint: PendingPoint | null = null;
  private pickerOpen = false;
  // Surfaced inline (not the full-page errorKey() above) when
  // undoMatchCompletion() refuses — round already advanced, or the next
  // match on this court already got scored.
  readonly cancelScoreErrorKey = signal<string | null>(null);

  /** Applies the point (a plain +1, same as simple mode — match pace never
   * waits on the detail dialog below) and opens the shared picker in the
   * SAME tap, before the request returns: the scorer starts on the detail
   * straight away instead of waiting out the round trip. What they do in
   * the picker before the point's score_event_id is known waits in
   * PendingPoint; if the point isn't applied after all, the picker closes.
   *
   * 032-freeze-while-picker-open: a match-ending point's realtime
   * match.ended push triggers a loadState() that blanks
   * liveState().current_match, which would make the @if hosting the picker
   * false and tear it down under the scorer. Freezing on the state captured
   * HERE, before the request is even sent, means nothing that arrives
   * afterward matters until this component lifts the freeze. */
  scoreThenOpenPicker(side: Team): void {
    if (this.connectionState() !== 'connected') {
      return;
    }
    const state = this.liveState();
    const currentMatch = state?.current_match;
    if (!state || !currentMatch || !this.scoreGuard.tryAcquire()) {
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
    this.frozenState.set(state);
    this.pickerOpen = true;
    this.shotPlacementPicker()?.open();

    this.courtControl
      .score(this.token, point.matchId, side, 1)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.scoreGuard.release();
          if (!result.applied || !result.score_event_id) {
            this.abandonPoint(point);
            return;
          }
          this.triggerScorePulse(side);
          const patched: CourtStateResponse = {
            ...state,
            current_match: {
              ...currentMatch,
              score_a: result.score_a,
              score_b: result.score_b,
              serve: result.serve,
            },
          };
          // Keep the backdrop on the new score while the picker is still
          // up. For a plain continuing point also commit the patch to the
          // real liveState() so the score is still correct once the freeze
          // lifts; for the match-ending point, leave liveState() alone —
          // whatever match.ended/next-round pushes arrive replace it
          // wholesale.
          if (this.pickerOpen && this.pendingPoint === point) {
            this.frozenState.set(patched);
          }
          if (result.status === 'in_progress') {
            this.liveState.set(patched);
          }
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
        .recordShotPlacement(
          this.token,
          point.matchId,
          scoreEventId,
          action.detail.rosterEntryId,
          action.detail.losingRosterEntryId,
          action.detail.landingX,
          action.detail.landingY,
          action.detail.endingType,
        )
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => this.clearPendingPoint(point));
      return;
    }

    this.cancelScoreErrorKey.set(null);
    // A point that just completed the match needs undoMatchCompletion()
    // instead of the plain -1 the control panel's own "-1" button uses:
    // see ScoreboardComponent's identical method for the full rationale.
    if (point.matchCompleted) {
      this.courtControl
        .undoMatchCompletion(this.token, point.matchId, point.side)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: () => {
            this.clearPendingPoint(point);
            this.loadState();
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
      .score(this.token, point.matchId, point.side, -1)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.scoreGuard.release();
          this.clearPendingPoint(point);
          this.patchLiveScore(point.side, result);
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
