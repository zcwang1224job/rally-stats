import { Component, effect, inject, input, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { GroupStandingsResponse } from '../../../core/api/group-member-view.models';
import { GroupMemberViewService } from '../group-member-view.service';

/** US2 (FR-005~010): 戰績頁——載入時查詢，無即時同步要求（spec
 * Assumptions）。四狀態（勝/敗/未上場/已離開）完全由後端推導，本元件
 * 僅負責呈現。 */
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
}
