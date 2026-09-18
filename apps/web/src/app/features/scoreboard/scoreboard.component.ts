import { Component, DestroyRef, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { ApiError } from '../../core/api/api-error';
import { CourtControlService } from '../../core/api/court-control.service';
import { CourtByTokenResponse } from '../../core/api/court-link.models';
import { CourtStateResponse, MatchLiveDetail, Team } from '../../core/api/court-live-state.models';
import { LinkHeartbeatService } from '../../core/api/link-heartbeat.service';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../core/realtime/reconnect-refetch.service';
import { ConfirmDialogComponent } from '../group-admin/shared/confirm-dialog.component';
import {
  ShotPlacementConfirmed,
  ShotPlacementPickerComponent,
} from '../shot-placement/shot-placement-picker.component';

/** 計分板：連結初始化/心跳（T042）+ link.regenerated 專屬失效提示
 * （T041，FR-035）+ 大字體即時比分/Round/即將登場顯示（007 US3，預設
 * 公開唯讀）。
 *
 * 018-plan-then-start follow-up: `canScore()`——當該團開啟
 * `scoreboard_scoring_enabled`（管理頁設定分頁的開關）時，`liveState()`
 * 會回傳 `scoreboard_scoring_enabled: true`，這裡才會顯示 +1/-1／提前結束
 * 操作，直接沿用控制板既有的 `CourtControlService.score()`/`endMatch()`
 * ——後端也是靠同一個旗標放行 `scoreboard_token` 呼叫這兩支 API（見
 * apps/api/app/domains/schedule/router.py `_can_score_by_token`），前端
 * 這裡只是「沒開的話乾脆不畫按鈕」，不是唯一的權限防線。預設關閉，所以
 * 沒特別設定的團，這個畫面跟以前完全一樣。 */
@Component({
  selector: 'app-scoreboard',
  imports: [TranslatePipe, ConfirmDialogComponent, ShotPlacementPickerComponent],
  templateUrl: './scoreboard.component.html',
  styleUrl: './scoreboard.component.scss',
})
export class ScoreboardComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly heartbeat = inject(LinkHeartbeatService);
  private readonly realtime = inject(RealtimeService);
  private readonly courtControl = inject(CourtControlService);
  private readonly reconnectRefetch = inject(ReconnectRefetchService);
  private readonly translate = inject(TranslateService);
  private readonly destroyRef = inject(DestroyRef);

  private readonly token = this.route.snapshot.paramMap.get('courtToken')!;
  private subscribedChannel: string | null = null;

  readonly courtInfo = signal<CourtByTokenResponse | null>(null);
  readonly liveState = signal<CourtStateResponse | null>(null);
  readonly linkInvalidated = signal(false);
  readonly loading = signal(true);
  readonly errorKey = signal<string | null>(null);

  /** 032-freeze-while-picker-open: a match-ending point triggers a
   * `match.ended` (and often `match.nextRound`) realtime push almost
   * immediately, which would otherwise call loadState() and swap
   * `liveState().current_match` out from under the still-open shot-
   * placement picker — destroying its `@if`-hosted DOM before the scorer
   * can respond. While non-null, the template renders THIS frozen snapshot
   * instead of the live one; scoreThenOpenPicker() sets it (with the just-
   * scored point's score already patched in) right before opening the
   * picker, and onShotPlacementClosed() clears it once the dialog is
   * actually closed (confirm/skip/cancelScore all end there), at which
   * point the template reverts to whatever liveState() has become by then. */
  private readonly frozenState = signal<CourtStateResponse | null>(null);
  readonly displayState = computed(() => this.frozenState() ?? this.liveState());

  readonly connectionState = this.realtime.connectionState;

  readonly canScore = computed(() => this.liveState()?.scoreboard_scoring_enabled === true);
  readonly endMatchDialog = viewChild<ConfirmDialogComponent>('endMatchDialog');
  readonly shotPlacementPicker = viewChild<ShotPlacementPickerComponent>('shotPlacementPicker');

  // Brief "pop" animation on a team's score number so a change is visible
  // at a glance (a spectator watching the board, not just the person
  // tapping +/-) rather than the digit silently jumping to a new value —
  // triggered only from the two spots below that represent a genuine score
  // change, never from a general loadState() refresh (initial load,
  // reconnect, rotation/round change), which would pulse on data that
  // hasn't actually changed.
  readonly scorePulseA = signal(false);
  readonly scorePulseB = signal(false);
  private readonly pulseTimeouts: Partial<Record<Team, ReturnType<typeof setTimeout>>> = {};

  // Already launched from a home-screen icon (manifest.json's "fullscreen"
  // display mode, or iOS's own standalone mode) — no browser chrome to hide,
  // so the Fullscreen API button isn't needed.
  // `(window.navigator as { standalone?: boolean }).standalone` is iOS
  // Safari's own pre-manifest flag; the two matchMedia checks are the
  // cross-browser standard — guarded by a `typeof` check since jsdom (this
  // project's test environment) doesn't implement `matchMedia` at all.
  private readonly isStandalone =
    (typeof window.matchMedia === 'function' &&
      (window.matchMedia('(display-mode: standalone)').matches ||
        window.matchMedia('(display-mode: fullscreen)').matches)) ||
    (window.navigator as { standalone?: boolean }).standalone === true;

  // Fullscreen API has no effect on iOS Safari/WebKit for a plain element
  // (only <video> supports it there) — `document.fullscreenEnabled` is the
  // standard feature-detection for this, so the button simply doesn't
  // render on iOS (no fullscreen path is offered there for now).
  readonly canRequestFullscreen = document.fullscreenEnabled && !this.isStandalone;
  readonly isFullscreen = signal(!!document.fullscreenElement);

  constructor() {
    const onFullscreenChange = (): void => this.isFullscreen.set(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onFullscreenChange);
    this.destroyRef.onDestroy(() => document.removeEventListener('fullscreenchange', onFullscreenChange));

    // FR-024: 重新連線後強制拉取最新完整狀態覆蓋本地暫存。
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
            return;
          }
          this.courtInfo.set(info);
          this.loading.set(false);
          if (!this.subscribedChannel) {
            // No login and so no language switcher of its own (unlike the
            // rest of the app) — display in whichever language the group's
            // creator/團長 last set for themselves, applied once up front
            // rather than on every heartbeat poll.
            this.translate.use(info.owner_language);
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
   * mid-animation from a previous change — clearing the class first and
   * re-applying it on the next frame is what actually restarts a CSS
   * animation (setting the same "true" value twice in a row wouldn't). */
  private triggerScorePulse(side: Team): void {
    const pulseSignal = side === 'A' ? this.scorePulseA : this.scorePulseB;
    clearTimeout(this.pulseTimeouts[side]);
    pulseSignal.set(false);
    requestAnimationFrame(() => {
      pulseSignal.set(true);
      // Matches .score--pulse's animation-duration (scoreboard.component.scss).
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
        if (data.link_type === 'scoreboard') {
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

  /** 029-serve-rotation-display FR-004/FR-006: resolves one of the four
   * station slots (`match.serve`'s `team_{a,b}_{right,left}_roster_entry_id`)
   * to the participant standing there — `null` for an empty slot (singles;
   * data-model.md's station fields are `null` there by design) or when
   * `serve` itself hasn't been computed yet (legacy match, research.md
   * Decision 4). `isServer` drives the non-purely-color marker (FR-005,
   * Constitution VII) — never the station's own presence/absence. */
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

  /** 同 ControlPanelComponent.score()——`canScore()` 已經在模板端決定按鈕
   * 要不要畫出來，這裡的 connectionState 判斷單純是離線時避免送出注定失敗
   * 的請求（FR-023），不是這個功能唯一的守門邏輯。 */
  score(side: Team, delta: 1 | -1): void {
    if (this.connectionState() !== 'connected') {
      return;
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
  // Captured once, right when the point is scored — onShotPlacementConfirmed()
  // and onShotPlacementCancelled() below use these rather than re-deriving
  // "the current match" from liveState()/frozenState() at the time the
  // scorer eventually acts, since a match-ending point can mean the court
  // has already moved on to a different match by then (frozenState only
  // holds the visible backdrop steady — it doesn't change which match these
  // two follow-up actions must target).
  private pendingMatchId: string | null = null;
  private pendingScoreEventId: string | null = null;
  // 032-cancel-score: whether the point that opened the picker was the
  // match-DECIDING one (result.status !== 'in_progress') — onShotPlacementCancelled()
  // below needs a different endpoint for that point specifically, since the
  // plain -1 correction can't touch an already-`completed` match at all.
  private pendingMatchCompleted = false;
  // Surfaced inline (not the full-page errorKey() above, which is reserved
  // for link/bootstrap failures) when undoMatchCompletion() above refuses —
  // e.g. the round already moved on, or the next match on this court has
  // already been scored — so the scorer isn't left silently wondering why
  // "取消得分" appeared to do nothing.
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
          // For a plain continuing point (status still 'in_progress') also
          // commit the patch to the real liveState() so the score is still
          // correct once the freeze lifts; for the match-ending point,
          // liveState() is left alone — whatever match.ended/next-round
          // pushes already arrived (or still will) replace it wholesale.
          this.frozenState.set(patched);
          if (result.status === 'in_progress') {
            this.liveState.set(patched);
          }
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
            // Shouldn't happen for an applied +1, but without a picker to
            // open there's nothing left to hold the freeze for.
            this.frozenState.set(null);
          }
        },
        error: () => this.frozenState.set(null),
      });
  }

  /** Bound to the picker's `(closed)` output — fires once the dialog is
   * actually closed, whichever of confirm/skip/cancelScore triggered it —
   * lifting the freeze so the template reverts to whatever liveState() has
   * become by then (already updated in the background if a match.ended /
   * next-round push arrived while the picker was up). */
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
        event.endingType,
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
   * of the plain -1 the scoreboard's own "-" button uses: apply_score_delta's
   * -1 correction requires status='in_progress', which this match no longer
   * is the instant it wins. undoMatchCompletion() can refuse (round already
   * moved on, or a replacement match pulled onto this court already got
   * scored) — that failure is surfaced via cancelScoreErrorKey rather than
   * silently leaving the match in its completed state. */
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
      });
  }

  openEndMatchDialog(): void {
    this.endMatchDialog()?.open();
  }

  confirmEndMatch(): void {
    if (this.connectionState() !== 'connected') {
      return;
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

  toggleFullscreen(): void {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => undefined);
    } else {
      document.documentElement.requestFullscreen().catch(() => undefined);
    }
  }
}
