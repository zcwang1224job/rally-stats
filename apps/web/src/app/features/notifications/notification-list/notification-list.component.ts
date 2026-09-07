import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { NotificationListResponse, NotificationSummary } from '../../../core/api/notification.models';
import { NotificationService } from '../notification.service';

/** US2/US3 (012): 通知列表——依時間新到舊、已讀/未讀狀態、全部標示已讀
 * （FR-004/005/008/013——本頁載入本身 MUST NOT 自動已讀，見
 * `NotificationService`）；點擊個別通知才轉為已讀並導向相關畫面
 * （FR-007）。 */
@Component({
  selector: 'app-notification-list',
  imports: [TranslatePipe, DatePipe],
  templateUrl: './notification-list.component.html',
  styleUrl: './notification-list.component.scss',
})
export class NotificationListComponent {
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);

  readonly records = signal<NotificationListResponse | null>(null);
  readonly errorKey = signal<string | null>(null);
  readonly page = signal(1);
  readonly pageNumbers = computed(() => {
    const totalPages = this.records()?.total_pages ?? 1;
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  });

  constructor() {
    this.load(this.page());
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load(page);
  }

  markAllRead(): void {
    this.notifications.markAllRead().subscribe(() => this.load(this.page()));
  }

  /** FR-007: marks the notification read, then navigates to the screen
   * where its underlying event can be viewed/handled. */
  open(notification: NotificationSummary): void {
    this.notifications.markRead(notification.notification_id).subscribe(() => {
      this.load(this.page());
      if (notification.type === 'friend_request') {
        void this.router.navigateByUrl('/friends/requests');
      }
    });
  }

  private load(page: number): void {
    this.notifications.list(page).subscribe({
      next: (response) => this.records.set(response),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }
}
