import { DatePipe } from '@angular/common';
import { Component, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import {
  GroupMatchRecordsResponse,
  MatchRecordDetailResponse,
  MatchRecordSummary,
} from '../../../core/api/group-member-view.models';
import { MatchRecordDetailDialogComponent } from '../../../core/match-record-detail/match-record-detail-dialog.component';
import { GroupMemberViewService } from '../group-member-view.service';

/** US3 (FR-011/012): 團內對戰紀錄——逐場列表，僅限本團，載入時查詢。
 * 016-match-score-timeline US1/US2/US3: 每列點擊開啟比賽詳情彈出視窗——
 * 呼叫本頁本來就已經在用的 `GroupMemberViewService`（見 research.md #4，
 * 刻意不透過任何「依 groupId 有無決定端點」的共用邏輯）。 */
@Component({
  selector: 'app-match-records',
  imports: [TranslatePipe, DatePipe, MatchRecordDetailDialogComponent],
  templateUrl: './match-records.component.html',
  styleUrl: './match-records.component.scss',
})
export class MatchRecordsComponent {
  readonly groupId = input.required<string>();

  private readonly memberView = inject(GroupMemberViewService);

  readonly records = signal<GroupMatchRecordsResponse | null>(null);
  readonly errorKey = signal<string | null>(null);
  readonly page = signal(1);
  readonly pageNumbers = computed(() => {
    const totalPages = this.records()?.total_pages ?? 1;
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  });

  private readonly detailDialogRef =
    viewChild.required<MatchRecordDetailDialogComponent>('detailDialog');
  readonly detail = signal<MatchRecordDetailResponse | null>(null);
  readonly detailLoading = signal(false);
  readonly detailLoadError = signal(false);

  constructor() {
    effect(() => {
      if (!this.groupId()) {
        return;
      }
      this.load(this.page());
    });
  }

  private load(page: number): void {
    this.memberView.getMatchRecords(this.groupId(), page).subscribe({
      next: (response) => this.records.set(response),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  goToPage(page: number): void {
    this.page.set(page);
  }

  openDetail(matchId: string): void {
    this.detail.set(null);
    this.detailLoadError.set(false);
    this.detailLoading.set(true);
    this.detailDialogRef().open();
    this.memberView.getMatchRecordDetail(this.groupId(), matchId).subscribe({
      next: (response) => {
        this.detail.set(response);
        this.detailLoading.set(false);
      },
      error: () => {
        this.detailLoadError.set(true);
        this.detailLoading.set(false);
      },
    });
  }

  /** The winning side's player names, joined — shown instead of a bare
   * "A方獲勝"/"B方獲勝": a Guest/Member reading their own group's history
   * cares who won, not which internal team letter was assigned to them. */
  winnerNames(match: MatchRecordSummary): string {
    const winners = match.winner_team === 'A' ? match.team_a : match.team_b;
    return winners.map((p) => p.nickname).join('、');
  }
}
