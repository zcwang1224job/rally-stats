import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { GroupMatchRecordsResponse } from '../../../core/api/group-member-view.models';
import { GroupMemberViewService } from '../group-member-view.service';

/** US3 (FR-011/012): 團內對戰紀錄——逐場列表，僅限本團，載入時查詢。 */
@Component({
  selector: 'app-match-records',
  imports: [TranslatePipe],
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
}
