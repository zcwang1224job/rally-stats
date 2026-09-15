import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { BindingStatusResponse } from '../../../core/api/group-join.models';
import { GuestBindingCtaComponent } from '../guest-binding-cta/guest-binding-cta.component';
import { GroupJoinService } from '../group-join.service';

type Status = 'loading' | 'error' | 'summary';

/** 015-manual-add-guest US2: entry point for the link/QR a 團長 shares
 * after manually adding a guest.
 *
 * 028-guest-stats-binding research.md #5: initialization now goes through
 * `getGuestBindingStatus()` first (permissive — works regardless of
 * roster/group active state) rather than jumping straight to
 * `resolveGuestSession()`, and branches three ways:
 * - already bound → this link's guest identity now belongs to an account;
 *   send the visitor to log in instead.
 * - not bound, still 現役 (roster active + group active) → unchanged
 *   behavior: seed this browser's guest session and forward into
 *   `GroupMemberViewComponent`, exactly like before this feature existed.
 * - not bound, 非現役 (left/kicked/disbanded) → `GroupMemberViewComponent`
 *   is built for a live, active view and its handling of a non-active
 *   roster/group was never verified for this feature (research.md #5), so
 *   this component renders a lightweight "個人戰績摘要" itself instead of
 *   navigating there. */
@Component({
  selector: 'app-guest-access',
  imports: [TranslatePipe, GuestBindingCtaComponent],
  templateUrl: './guest-access.component.html',
})
export class GuestAccessComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly joinService = inject(GroupJoinService);

  readonly status = signal<Status>('loading');
  readonly errorKey = signal<string | null>(null);
  readonly summary = signal<BindingStatusResponse | null>(null);
  private token = '';

  constructor() {
    const token = this.route.snapshot.paramMap.get('token');
    if (!token) {
      this.status.set('error');
      this.errorKey.set('errors.LINK_NOT_FOUND');
      return;
    }
    this.token = token;

    this.joinService.getGuestBindingStatus(token).subscribe({
      next: (status) => {
        if (status.already_bound) {
          // Bug fix: a stale stored token (from an earlier visit that
          // successfully bound, e.g. via OAuth's own redirect-back) MUST
          // NOT linger — leaving it would make GroupMemberViewComponent
          // treat this browser as still-Guest on its own next load.
          this.joinService.clearGuestSessionToken(status.group_id);
          void this.router.navigate(['/auth/login']);
          return;
        }
        if (status.group_status === 'active' && status.roster_status === 'active') {
          this.joinService.setGuestSessionToken(status.group_id, token);
          this.joinService.setActiveGuestGroupId(status.group_id);
          void this.router.navigate(['/groups', status.group_id, 'member-view']);
          return;
        }
        this.status.set('summary');
        this.summary.set(status);
      },
      error: (error: ApiError) => {
        this.status.set('error');
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  get guestSessionToken(): string {
    return this.token;
  }

  onBound(): void {
    // FR-005: re-check status so the CTA disappears and the "already
    // bound" view takes over — the same single source of truth the
    // constructor used, not a locally-guessed state flip.
    this.joinService.getGuestBindingStatus(this.token).subscribe({
      next: (status) => {
        this.summary.set(status);
        if (status.already_bound) {
          this.joinService.clearGuestSessionToken(status.group_id);
        }
      },
    });
  }
}
