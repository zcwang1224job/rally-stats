import { Component, DestroyRef, inject, input, output, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslatePipe } from '@ngx-translate/core';
import { CourtControlService } from '../../../core/api/court-control.service';
import { CourtLiveState, Team } from '../../../core/api/court-live-state.models';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { ConfirmDialogComponent } from '../../group-admin/shared/confirm-dialog.component';

/** 全部場地控制板中單一場地的操作區塊（007 US5）——每個場地一個獨立
 * 元件實例，版面天然區隔避免誤按（FR-001），且各自的確認彈窗
 * viewChild 不會互相衝突（比照管理頁 court-control 元件的設計）。與單一
 * 場地控制板/管理頁完全相同的業務規則，僅差在走全部場地 token 這組
 * 端點。 */
@Component({
  selector: 'app-all-courts-court-block',
  imports: [TranslatePipe, ConfirmDialogComponent],
  templateUrl: './all-courts-court-block.component.html',
  styleUrl: './all-courts-court-block.component.scss',
})
export class AllCourtsCourtBlockComponent {
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
