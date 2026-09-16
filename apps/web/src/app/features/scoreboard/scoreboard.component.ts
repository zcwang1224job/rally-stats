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
  imports: [TranslatePipe, ConfirmDialogComponent],
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

  readonly connectionState = this.realtime.connectionState;

  readonly canScore = computed(() => this.liveState()?.scoreboard_scoring_enabled === true);
  readonly endMatchDialog = viewChild<ConfirmDialogComponent>('endMatchDialog');

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
  station(match: MatchLiveDetail, rosterEntryId: string | null): { nickname: string; isServer: boolean } | null {
    if (!rosterEntryId) {
      return null;
    }
    const participant = match.participants.find((p) => p.roster_entry_id === rosterEntryId);
    if (!participant) {
      return null;
    }
    return { nickname: participant.nickname, isServer: match.serve?.server_roster_entry_id === rosterEntryId };
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
            current_match: { ...state.current_match, score_a: result.score_a, score_b: result.score_b },
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
