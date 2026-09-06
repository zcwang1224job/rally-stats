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

/** 單一場地控制板：連結初始化/心跳（T042）+ link.regenerated 專屬失效
 * 提示（T041，FR-035）+ +1/-1／提前結束操作與即時狀態顯示（007
 * US1/US2）。 */
@Component({
  selector: 'app-control-panel',
  imports: [TranslatePipe, ConfirmDialogComponent],
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

  readonly connectionState = this.realtime.connectionState;

  readonly endMatchDialog = viewChild<ConfirmDialogComponent>('endMatchDialog');

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
