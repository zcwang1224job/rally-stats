import { Component, inject, input, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { ScheduleService } from './schedule.service';
import { PartnershipsResponse } from './schedule.models';

/** 搭檔設定區塊 (US4, T062). 列出目前所有搭檔組合與落單者；管理員選擇任兩位
 * 參與者重新組成一組（FR-021）——後端負責拆散雙方原本的搭檔。 */
@Component({
  selector: 'app-partnership-settings',
  imports: [TranslatePipe],
  templateUrl: './partnership-settings.component.html',
  styleUrl: './partnership-settings.component.scss',
})
export class PartnershipSettingsComponent {
  readonly groupId = input.required<string>();

  private readonly scheduleService = inject(ScheduleService);

  readonly partnerships = signal<PartnershipsResponse | null>(null);
  readonly loading = signal(true);
  readonly errorKey = signal<string | null>(null);
  readonly firstPick = signal<string | null>(null);

  constructor() {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.scheduleService.getPartnerships(this.groupId()).subscribe({
      next: (response) => {
        this.partnerships.set(response);
        this.loading.set(false);
      },
      error: (error: ApiError) => {
        this.loading.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  allMembers(): { roster_entry_id: string; nickname: string }[] {
    const data = this.partnerships();
    if (!data) return [];
    const fromPairs = data.partnerships.flatMap((p) => [p.player_a, p.player_b]);
    return [...fromPairs, ...data.unpaired];
  }

  pick(rosterEntryId: string): void {
    const first = this.firstPick();
    if (!first) {
      this.firstPick.set(rosterEntryId);
      return;
    }
    if (first === rosterEntryId) {
      this.firstPick.set(null);
      return;
    }
    this.errorKey.set(null);
    this.scheduleService.reassignPartnership(this.groupId(), first, rosterEntryId).subscribe({
      next: (response) => {
        this.partnerships.set(response);
        this.firstPick.set(null);
      },
      error: (error: ApiError) => {
        this.errorKey.set(error.i18nKey);
        this.firstPick.set(null);
      },
    });
  }
}
