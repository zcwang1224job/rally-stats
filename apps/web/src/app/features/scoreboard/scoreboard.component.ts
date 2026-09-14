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
import { ConfirmDialogComponent } from '../group-admin/shared/confirm-dialog.component';
import { LanguageSwitcherComponent } from '../../core/language/language-switcher.component';

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
  imports: [TranslatePipe, ConfirmDialogComponent, LanguageSwitcherComponent],
  templateUrl: './scoreboard.component.html',
  styleUrl: './scoreboard.component.scss',
})
export class ScoreboardComponent {
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

  readonly connectionState = this.realtime.connectionState;

  readonly canScore = computed(() => this.liveState()?.scoreboard_scoring_enabled === true);
  readonly endMatchDialog = viewChild<ConfirmDialogComponent>('endMatchDialog');

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
        if (data.link_type === 'scoreboard') {
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
