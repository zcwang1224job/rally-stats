import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslateService } from '@ngx-translate/core';
import { NotificationService } from '../notification.service';

/** Unread-notification badge (FR-006) — lives in `nav-shell` so it's
 * visible from every main page a signed-in member sees, independent of
 * whether the mobile hamburger menu is open. Caps its displayed count at
 * "99+" past 99 (spec.md Clarifications session 2026-09-07); the
 * `aria-label` always states the real number so screen reader users never
 * lose precision to the visual cap. */
@Component({
  selector: 'app-notification-bell',
  imports: [RouterLink],
  templateUrl: './notification-bell.component.html',
  styleUrl: './notification-bell.component.scss',
})
export class NotificationBellComponent {
  private readonly notifications = inject(NotificationService);
  private readonly translate = inject(TranslateService);

  readonly unreadCount = this.notifications.unreadCount;
  readonly displayCount = computed(() => {
    const count = this.unreadCount();
    return count > 99 ? '99+' : String(count);
  });

  readonly ariaLabel = computed(() =>
    this.translate.instant('notifications.bell.ariaLabel', { count: this.unreadCount() }),
  );
}
