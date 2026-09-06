import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { MemberPublic } from '../../core/api/member-auth.models';
import { AuthService } from '../auth/auth.service';

/** Member home page (006). Real implementation replacing the pre-006
 * placeholder: fetches the signed-in member and, per FR-012/019, redirects
 * to /member/settings when `nickname === null` (first-login setup) before
 * showing anything else. */
@Component({
  selector: 'app-member',
  imports: [TranslatePipe, RouterLink],
  templateUrl: './member.component.html',
  styleUrl: './member.component.scss',
})
export class MemberComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly loading = signal(true);
  readonly member = signal<MemberPublic | null>(null);

  constructor() {
    if (!this.auth.isLoggedIn()) {
      void this.router.navigate(['/auth/login']);
      return;
    }
    this.auth.getMe().subscribe({
      next: (member) => {
        this.loading.set(false);
        if (member.nickname === null) {
          void this.router.navigate(['/member/settings']);
          return;
        }
        this.member.set(member);
      },
      error: () => {
        this.auth.clearTokens();
        void this.router.navigate(['/auth/login']);
      },
    });
  }

  logout(): void {
    this.auth.logout();
    void this.router.navigateByUrl('/');
  }
}
