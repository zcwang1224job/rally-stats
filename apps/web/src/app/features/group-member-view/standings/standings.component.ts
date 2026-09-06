import { Component, effect, inject, input, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { GroupStandingsResponse, MemberStandingRow } from '../../../core/api/group-member-view.models';
import { GroupMemberViewService } from '../group-member-view.service';

export interface WinLossRecord {
  wins: number;
  losses: number;
}

/** US2 (FR-005~010): 戰績頁——載入時查詢，無即時同步要求（spec
 * Assumptions）。每一輪的勝敗數直接來自後端（011-round-robin-scheduling：
 * 循環賽單打一輪內一個人可能打好幾場，所以是「這一輪」的勝敗計數，不是
 * 單一輸贏狀態）——本元件只負責呈現跟算總計，不重新推導每輪本身的數字。 */
@Component({
  selector: 'app-standings',
  imports: [TranslatePipe],
  templateUrl: './standings.component.html',
  styleUrl: './standings.component.scss',
})
export class StandingsComponent {
  readonly groupId = input.required<string>();

  private readonly memberView = inject(GroupMemberViewService);

  readonly standings = signal<GroupStandingsResponse | null>(null);
  readonly errorKey = signal<string | null>(null);

  constructor() {
    effect(() => {
      if (!this.groupId()) {
        return;
      }
      this.memberView.getStandings(this.groupId()).subscribe({
        next: (response) => this.standings.set(response),
        error: (error: ApiError) => this.errorKey.set(error.i18nKey),
      });
    });
  }

  /** did_not_play/left rounds carry no wins/losses to show — this is the
   * "should this cell show a win/loss count" guard. */
  hasRecord(member: MemberStandingRow, round: number): boolean {
    const record = member.rounds[String(round)];
    return record !== undefined && !record.left && (record.wins > 0 || record.losses > 0);
  }

  totalRecord(member: MemberStandingRow): WinLossRecord {
    const rounds = this.standings()?.rounds ?? [];
    let wins = 0;
    let losses = 0;
    for (const round of rounds) {
      const record = member.rounds[String(round)];
      if (record) {
        wins += record.wins;
        losses += record.losses;
      }
    }
    return { wins, losses };
  }
}
