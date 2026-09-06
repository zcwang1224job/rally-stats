import { Component, DestroyRef, effect, inject, input, output, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslatePipe } from '@ngx-translate/core';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../../core/realtime/reconnect-refetch.service';
import { ConfirmDialogComponent } from '../shared/confirm-dialog.component';
import { ScheduleService } from './schedule.service';
import { CourtScheduleStatus, Team } from './schedule.models';

/** 管理頁「場地控制」區塊之單一場地操作元件（007 US4）——與公開控制板
 * 完全相同的比分/提前結束業務規則，唯一差異是走管理員 PIN session 驗證
 * 路徑而非 token（research.md #10）。斷線提示/操作限制/重連強制覆蓋
 * （FR-021~025）比照公開控制板同一套規則。 */
@Component({
  selector: 'app-court-control',
  imports: [TranslatePipe, ConfirmDialogComponent],
  templateUrl: './court-control.component.html',
  styleUrl: './court-control.component.scss',
})
export class CourtControlComponent {
  readonly groupId = input.required<string>();
  readonly court = input.required<CourtScheduleStatus>();
  readonly changed = output<void>();

  private readonly scheduleService = inject(ScheduleService);
  private readonly realtime = inject(RealtimeService);
  private readonly reconnectRefetch = inject(ReconnectRefetchService);
  private readonly destroyRef = inject(DestroyRef);

  readonly connectionState = this.realtime.connectionState;
  readonly endMatchDialog = viewChild<ConfirmDialogComponent>('endMatchDialog');

  private subscribedChannel: string | null = null;

  constructor() {
    this.reconnectRefetch
      .onReconnect()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.changed.emit());

    // 場地 court_id 一旦確定（掛載後恆定不變）即訂閱一次頻道；`schedule`
    // 每次重新整理都會建立新的 CourtScheduleStatus 物件，但同一場地的
    // court_id 不變，故只需訂閱一次，不隨每次 changed 事件重複訂閱。
    effect(() => {
      const channel = `court:${this.groupId()}:${this.court().court_id}`;
      if (this.subscribedChannel === channel) {
        return;
      }
      this.subscribedChannel = channel;
      for (const event of [
        'match.scoreUpdated',
        'match.ended',
        'rotation.updated',
        'match.nextRound',
      ]) {
        this.realtime
          .subscribe(channel, event)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe(() => this.changed.emit());
      }
    });
  }

  score(side: Team, delta: 1 | -1): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-023
    }
    const matchId = this.court().current_match?.match_id;
    if (!matchId) {
      return;
    }
    this.scheduleService
      .scoreMatch(this.groupId(), this.court().court_id, matchId, side, delta)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.changed.emit());
  }

  openEndMatchDialog(): void {
    this.endMatchDialog()?.open();
  }

  confirmEndMatch(): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-023
    }
    const matchId = this.court().current_match?.match_id;
    if (!matchId) {
      return;
    }
    this.scheduleService
      .endMatch(this.groupId(), this.court().court_id, matchId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.changed.emit());
  }
}
