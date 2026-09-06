import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../core/api/api-error';
import { CourtControlService } from '../../core/api/court-control.service';
import { CourtByTokenResponse } from '../../core/api/court-link.models';
import { CourtStateResponse } from '../../core/api/court-live-state.models';
import { LinkHeartbeatService } from '../../core/api/link-heartbeat.service';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../core/realtime/reconnect-refetch.service';

/** 計分板：連結初始化/心跳（T042）+ link.regenerated 專屬失效提示
 * （T041，FR-035）+ 大字體即時比分/Round/即將登場顯示（007 US3，公開
 * 唯讀，不提供任何操作）。 */
@Component({
  selector: 'app-scoreboard',
  imports: [TranslatePipe],
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

  constructor() {
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
}
