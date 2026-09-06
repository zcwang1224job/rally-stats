import { Component, computed, inject, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { MemberMatchRecordsResponse } from '../../../core/api/group-member-view.models';
import { AuthService } from '../../auth/auth.service';

/** US5 (FR-017~020): 會員頁面「對戰紀錄」——跨團已完成比賽 + 彙總勝負
 * 統計，僅登入會員可見（路由層由既有 member 功能區塊之登入檢查涵蓋）。 */
@Component({
  selector: 'app-match-history',
  imports: [TranslatePipe],
  templateUrl: './match-history.component.html',
  styleUrl: './match-history.component.scss',
})
export class MatchHistoryComponent {
  private readonly auth = inject(AuthService);

  readonly records = signal<MemberMatchRecordsResponse | null>(null);
  readonly errorKey = signal<string | null>(null);
  readonly page = signal(1);
  readonly pageNumbers = computed(() => {
    const totalPages = this.records()?.total_pages ?? 1;
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  });

  constructor() {
    this.load(this.page());
  }

  private load(page: number): void {
    this.auth.getMatchRecords(page).subscribe({
      next: (response) => this.records.set(response),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load(page);
  }
}
