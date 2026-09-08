import { Component, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { AuthService } from '../../features/auth/auth.service';
import { NotificationBellComponent } from '../../features/notifications/notification-bell/notification-bell.component';
import { NotificationService } from '../../features/notifications/notification.service';

/** Global nav shell (009) — rendered from the app root on every route that
 * doesn't opt out via `data.navShell: false` (see app.routes.ts). Not used
 * on group-member-view (has its own bottom nav), the admin page (PIN
 * session, not member login), or any QR/deep-link courtside screen. Also
 * the sole place `NotificationService.init()` is called (012) — it's the
 * one component guaranteed to render on every main page a signed-in
 * member sees (FR-006). */
@Component({
  selector: 'app-nav-shell',
  imports: [RouterLink, TranslatePipe, NotificationBellComponent],
  templateUrl: './nav-shell.component.html',
  styleUrl: './nav-shell.component.scss',
})
export class NavShellComponent {
  private readonly auth = inject(AuthService);
  private readonly notifications = inject(NotificationService);

  readonly loggedIn = this.auth.loggedIn;
  readonly open = signal(false);

  constructor() {
    effect(() => {
      if (this.loggedIn()) {
        this.notifications.init();
      } else {
        // Logout is a pure client-side state change (no reload) — without
        // this, a different member logging in on the same tab would stay
        // wired to the previous member's channel/unread count.
        this.notifications.reset();
      }
    });
  }

  toggleOpen(): void {
    this.open.update((value) => !value);
  }

  closeMenu(): void {
    this.open.set(false);
  }
}
