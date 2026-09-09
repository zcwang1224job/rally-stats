import { Component, effect, inject, input, output, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { PartnerSource } from '../group-admin.models';
import { ScheduleService } from './schedule.service';
import { PartnershipsResponse, RosterSummary, TemporaryPairing } from './schedule.models';

/** 搭檔設定區塊 (US4, T062). 列出目前所有搭檔組合與落單者；管理員選擇任兩位
 * 參與者重新組成一組（FR-021）——後端負責拆散雙方原本的搭檔。
 *
 * 017-fixed-partner-autofill (FR-001/FR-006): `partnerSource === 'manual'`
 * 且仍有未配對成員時，額外提供「剩下的人隨機配對」預覽——這份暫時配對
 * 全程留在前端（研究決策 #1），只有在管理員「產生下一輪賽程」時才會被
 * 讀取（透過 `temporaryPairingsChange` 往父層回報），本元件本身完全
 * 不呼叫任何寫入端點。調整暫時配對的互動範圍 MUST 只限於目前這份暫時
 * 配對涵蓋的成員（FR-006）——MUST NOT 讓已有正式搭檔的成員被選入。 */
@Component({
  selector: 'app-partnership-settings',
  imports: [TranslatePipe],
  templateUrl: './partnership-settings.component.html',
  styleUrl: './partnership-settings.component.scss',
})
export class PartnershipSettingsComponent {
  readonly groupId = input.required<string>();
  readonly partnerSource = input.required<PartnerSource>();

  readonly temporaryPairingsChange = output<TemporaryPairing[]>();

  private readonly scheduleService = inject(ScheduleService);

  readonly partnerships = signal<PartnershipsResponse | null>(null);
  readonly loading = signal(true);
  readonly errorKey = signal<string | null>(null);
  readonly firstPick = signal<string | null>(null);

  readonly temporaryMembers = signal<RosterSummary[]>([]);
  readonly temporaryPairs = signal<TemporaryPairing[]>([]);
  readonly temporaryFirstPick = signal<string | null>(null);
  readonly previewLoading = signal(false);
  readonly previewErrorKey = signal<string | null>(null);

  constructor() {
    // Signal inputs aren't resolved yet at constructor time (NG0950) — defer
    // the initial load to an effect, same pattern as StandingsComponent.
    effect(() => {
      if (!this.groupId()) {
        return;
      }
      this.load();
    });
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

  isSelected(rosterEntryId: string): boolean {
    return this.firstPick() === rosterEntryId;
  }

  isTemporarySelected(rosterEntryId: string): boolean {
    return this.temporaryFirstPick() === rosterEntryId;
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

  /** 直接拆散一組正式搭檔——不透過「點兩人互換」(`pick`) 間接觸發，涵蓋
   * 現役成員只剩下這唯一一組搭檔（沒有第三人可以互換）時，管理員原本完全
   * 無法讓他們變成落單的邊界情況。 */
  dissolve(rosterEntryId: string): void {
    this.errorKey.set(null);
    this.firstPick.set(null);
    this.scheduleService.dissolvePartnership(this.groupId(), rosterEntryId).subscribe({
      next: (response) => {
        this.partnerships.set(response);
      },
      error: (error: ApiError) => {
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  previewRandomPairing(): void {
    this.previewErrorKey.set(null);
    this.previewLoading.set(true);
    this.scheduleService.previewRandomPairing(this.groupId()).subscribe({
      next: (response) => {
        this.previewLoading.set(false);
        this.temporaryPairs.set(response.pairings);
        this.temporaryMembers.set(response.pairings.flatMap((p) => [p.player_a, p.player_b]));
        this.temporaryFirstPick.set(null);
        this.temporaryPairingsChange.emit(response.pairings);
      },
      error: (error: ApiError) => {
        this.previewLoading.set(false);
        this.previewErrorKey.set(error.i18nKey);
      },
    });
  }

  /** 目前暫時配對中「沒有被配到一組」的成員——不論是預覽剛回來時的落單，
   * 或是被 `pickTemporary` 重新配對後被拆散出來的舊搭檔；這些人在
   * 「產生下一輪賽程」時會由後端自動補齊配對（FR-002）。 */
  temporaryUnpaired(): RosterSummary[] {
    const pairedIds = new Set(
      this.temporaryPairs().flatMap((pair) => [
        pair.player_a.roster_entry_id,
        pair.player_b.roster_entry_id,
      ]),
    );
    return this.temporaryMembers().filter((member) => !pairedIds.has(member.roster_entry_id));
  }

  /** FR-006：與既有 `pick()` 完全相同的「點兩人互換」操作方式，但選取
   * 對象僅限於目前這份暫時配對涵蓋的成員（`temporaryMembers()`）——本方法
   * 從未被綁定到正式搭檔清單的任何按鈕上，因此已有正式搭檔的成員從一開始
   * 就無法被選入這個互動。 */
  pickTemporary(rosterEntryId: string): void {
    const first = this.temporaryFirstPick();
    if (!first) {
      this.temporaryFirstPick.set(rosterEntryId);
      return;
    }
    if (first === rosterEntryId) {
      this.temporaryFirstPick.set(null);
      return;
    }
    this.reassignTemporary(first, rosterEntryId);
    this.temporaryFirstPick.set(null);
  }

  private reassignTemporary(aId: string, bId: string): void {
    const members = this.temporaryMembers();
    const memberA = members.find((m) => m.roster_entry_id === aId);
    const memberB = members.find((m) => m.roster_entry_id === bId);
    if (!memberA || !memberB) return;

    const remaining = this.temporaryPairs().filter(
      (pair) =>
        pair.player_a.roster_entry_id !== aId &&
        pair.player_b.roster_entry_id !== aId &&
        pair.player_a.roster_entry_id !== bId &&
        pair.player_b.roster_entry_id !== bId,
    );
    const updated = [...remaining, { player_a: memberA, player_b: memberB }];
    this.temporaryPairs.set(updated);
    this.temporaryPairingsChange.emit(updated);
  }
}
