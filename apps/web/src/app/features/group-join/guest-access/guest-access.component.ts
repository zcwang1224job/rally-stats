import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { GroupJoinService } from '../group-join.service';

type Status = 'loading' | 'error';

/** 015-manual-add-guest US2: entry point for the link/QR a 團長 shares
 * after manually adding a guest — resolves the token via the existing
 * `resolveGuestSession()` (previously only used for same-browser session
 * restore, see research.md #3), seeds this browser's guest session exactly
 * like a self-join would, then forwards into the same member-view a
 * self-joined guest lands on. Mirrors `GroupJoinComponent`'s
 * resolve-then-redirect structure. */
@Component({
  selector: 'app-guest-access',
  imports: [TranslatePipe],
  templateUrl: './guest-access.component.html',
})
export class GuestAccessComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly joinService = inject(GroupJoinService);

  readonly status = signal<Status>('loading');
  readonly errorKey = signal<string | null>(null);

  constructor() {
    const token = this.route.snapshot.paramMap.get('token');
    if (!token) {
      this.status.set('error');
      this.errorKey.set('errors.LINK_NOT_FOUND');
      return;
    }
    this.joinService.resolveGuestSession(token).subscribe({
      next: (session) => {
        this.joinService.setGuestSessionToken(session.group_id, token);
        this.joinService.setActiveGuestGroupId(session.group_id);
        void this.router.navigate(['/groups', session.group_id, 'member-view']);
      },
      error: (error: ApiError) => {
        this.status.set('error');
        this.errorKey.set(error.i18nKey);
      },
    });
  }
}
