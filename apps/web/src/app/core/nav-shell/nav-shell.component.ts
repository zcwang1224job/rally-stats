import { Component, effect, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
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
  private readonly router = inject(Router);
  private readonly notifications = inject(NotificationService);

  readonly loggedIn = this.auth.loggedIn;
  readonly open = signal(false);

  constructor() {
    effect(() => {
      if (this.loggedIn()) {
        this.notifications.init();
      }
    });
  }

  toggleOpen(): void {
    this.open.update((value) => !value);
  }

  closeMenu(): void {
    this.open.set(false);
  }

  onLogout(): void {
    this.auth.logout();
    this.open.set(false);
    void this.router.navigateByUrl('/');
  }
}
