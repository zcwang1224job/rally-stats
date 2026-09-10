import { Component, DestroyRef, effect, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../../core/realtime/reconnect-refetch.service';
import { GroupStandingsResponse, MemberStandingRow } from '../../../core/api/group-member-view.models';
import { GroupMemberViewService } from '../group-member-view.service';

export interface WinLossRecord {
  wins: number;
  losses: number;
}

/** US2 (005-member-view，FR-005~010): 戰績頁。
 *
 * 018-group-leaderboard 疊加：`members` 已由後端依 `rank` 排序好
 * （constitution X——本元件 MUST NOT 自行重新排序/計算名次，只負責渲染
 * `rank`/`total_wins`/`total_losses`，見 data-model.md）；訂閱既有
 * `group:{groupId}:notifications` 頻道的 `standings.updated` 事件（比照
 * `notification.service.ts` 既有的「收到事件就整包重新拉取」模式），並
 * 重用既有 `ReconnectRefetchService` 讓斷線重連/切回畫面時自動拿到最新
 * 名次（FR-012）——本畫面純唯讀，刻意不新增任何「連線中斷」提示元件。 */
@Component({
  selector: 'app-standings',
  imports: [TranslatePipe],
  templateUrl: './standings.component.html',
  styleUrl: './standings.component.scss',
})
export class StandingsComponent {
  readonly groupId = input.required<string>();

  private readonly memberView = inject(GroupMemberViewService);
  private readonly realtime = inject(RealtimeService);
  private readonly reconnectRefetch = inject(ReconnectRefetchService);
  private readonly destroyRef = inject(DestroyRef);

  readonly standings = signal<GroupStandingsResponse | null>(null);
  readonly errorKey = signal<string | null>(null);
  readonly myRosterEntryId = signal<string | null>(null);

  private subscribedGroupId: string | null = null;

  constructor() {
    effect(() => {
      const groupId = this.groupId();
      if (!groupId) {
        return;
      }
      this.load(groupId);
      this.memberView.resolveRosterEntryId(groupId).subscribe((rosterEntryId) => {
        this.myRosterEntryId.set(rosterEntryId);
      });
      this.subscribeToChannel(groupId);
    });

    // `onReconnect()` calls `toObservable()` internally, which requires an
    // injection context — MUST be called here (constructor top level), not
    // from inside the effect above (an effect body is explicitly NOT an
    // injection context, NG0203). `groupId()` is read fresh inside the
    // callback so this one subscription always refetches for whichever
    // group is current when a reconnect actually happens.
    this.reconnectRefetch
      .onReconnect()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        const groupId = this.groupId();
        if (groupId) {
          this.load(groupId);
        }
      });
  }

  private load(groupId: string): void {
    this.memberView.getStandings(groupId).subscribe({
      next: (response) => this.standings.set(response),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  private subscribeToChannel(groupId: string): void {
    if (this.subscribedGroupId === groupId) {
      return;
    }
    this.subscribedGroupId = groupId;
    this.realtime
      .subscribe(`group:${groupId}:notifications`, 'standings.updated')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load(groupId));
  }

  isSelf(member: MemberStandingRow): boolean {
    const mine = this.myRosterEntryId();
    return mine !== null && mine === member.roster_entry_id;
  }

  /** FR-007/SC-004: "尚無比賽紀錄" — zero wins AND zero losses across every
   * round means this member has never had a completed match. */
  hasNoRecordYet(member: MemberStandingRow): boolean {
    return member.total_wins === 0 && member.total_losses === 0;
  }

  /** did_not_play/left rounds carry no wins/losses to show — this is the
   * "should this cell show a win/loss count" guard. */
  hasRecord(member: MemberStandingRow, round: number): boolean {
    const record = member.rounds[String(round)];
    return record !== undefined && !record.left && (record.wins > 0 || record.losses > 0);
  }

  totalRecord(member: MemberStandingRow): WinLossRecord {
    return { wins: member.total_wins, losses: member.total_losses };
  }
}
