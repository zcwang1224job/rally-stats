import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { CourtControlService } from '../../../core/api/court-control.service';
import { AllCourtsLiveState, CourtLiveState } from '../../../core/api/court-live-state.models';
import { LinkHeartbeatService } from '../../../core/api/link-heartbeat.service';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../../core/realtime/reconnect-refetch.service';
import { AllCourtsCourtSummary } from './all-courts-control-panel.models';
import { AllCourtsCourtBlockComponent } from './all-courts-court-block.component';

/** 全部場地控制板（007 US5）——同一畫面依序操作團內所有場地，各場地
 * 版面獨立區隔避免誤按（FR-001）；不提供任何 Next Round 操作入口
 * （FR-014，SC-004）。連結初始化/心跳（T042）+ link.regenerated 專屬
 * 失效提示（T041，FR-035）沿用既有骨架，新增即時比分/斷線重連。 */
@Component({
  selector: 'app-all-courts-control-panel',
  imports: [TranslatePipe, AllCourtsCourtBlockComponent],
  templateUrl: './all-courts-control-panel.component.html',
  styleUrl: './all-courts-control-panel.component.scss',
})
export class AllCourtsControlPanelComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly heartbeat = inject(LinkHeartbeatService);
  private readonly realtime = inject(RealtimeService);
  private readonly courtControl = inject(CourtControlService);
  private readonly reconnectRefetch = inject(ReconnectRefetchService);
  private readonly destroyRef = inject(DestroyRef);

  readonly token = this.route.snapshot.paramMap.get('allCourtsToken')!;
  private subscribedGroupId: string | null = null;
  private readonly subscribedCourtChannels = new Set<string>();

  readonly courts = signal<AllCourtsCourtSummary[]>([]);
  readonly liveState = signal<AllCourtsLiveState | null>(null);
  readonly groupDisbanded = signal(false);
  readonly linkInvalidated = signal(false);
  readonly loading = signal(true);
  readonly errorKey = signal<string | null>(null);

  readonly connectionState = this.realtime.connectionState;

  constructor() {
    this.reconnectRefetch
      .onReconnect()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadState());

    this.heartbeat
      .watchAllCourtsLink(this.token)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          if (this.linkInvalidated()) {
            return; // stale connection's link already superseded — ignore
          }
          this.courts.set(response.courts);
          this.groupDisbanded.set(response.group_disbanded);
          this.loading.set(false);
          if (!this.subscribedGroupId) {
            this.subscribeToChanges(response.group_id);
            this.loadState();
          }
          this.subscribeToCourtChannels(response.group_id, response.courts);
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

  stateFor(courtId: string): CourtLiveState | null {
    return this.liveState()?.courts.find((c) => c.court_id === courtId) ?? null;
  }

  refreshState(): void {
    this.loadState();
  }

  private loadState(): void {
    this.courtControl
      .getAllCourtsState(this.token)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((state) => this.liveState.set(state));
  }

  private subscribeToChanges(groupId: string): void {
    this.subscribedGroupId = groupId;
    const channel = `group:${groupId}:notifications`;

    this.realtime
      .subscribe(channel, 'court.added')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((message) => {
        const data = message.data as AllCourtsCourtSummary;
        this.courts.update((list) => [...list, data]);
        this.loadState();
      });

    this.realtime
      .subscribe(channel, 'court.deleted')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((message) => {
        const data = message.data as { court_id: string };
        this.courts.update((list) => list.filter((c) => c.court_id !== data.court_id));
      });

    this.realtime
      .subscribe(channel, 'group.disbanded')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.groupDisbanded.set(true));

    this.realtime
      .subscribe(channel, 'link.regenerated')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((message) => {
        const data = message.data as { link_type: string };
        if (data.link_type === 'all_courts') {
          this.linkInvalidated.set(true);
        }
      });
  }

  private subscribeToCourtChannels(groupId: string, courts: AllCourtsCourtSummary[]): void {
    for (const court of courts) {
      const channel = `court:${groupId}:${court.court_id}`;
      if (this.subscribedCourtChannels.has(channel)) {
        continue;
      }
      this.subscribedCourtChannels.add(channel);
      for (const event of [
        'match.scoreUpdated',
        'match.ended',
        'rotation.updated',
        'match.nextRound',
      ]) {
        this.realtime
          .subscribe(channel, event)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe(() => this.loadState());
      }
    }
  }
}
