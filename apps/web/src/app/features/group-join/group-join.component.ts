import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../core/api/api-error';
import { GroupJoinService } from './group-join.service';

type Status = 'loading' | 'error' | 'disbanded' | 'full' | 'restored';

/** Join-link / QR Code entry point (US2, FR-008~010): resolves the token,
 * then either shows a clear blocking screen (disbanded/full/invalid link,
 * FR-009) or forwards into the same join-flow US1 already built — the rest
 * of the flow is identical regardless of entry point.
 *
 * US6 (FR-020a): when the preview signals `already_joined` (a logged-in
 * member who's already active here), this joins directly instead of
 * navigating into join-flow — no password/nickname re-entry, no re-running
 * the capacity check, matching the Guest-token-restore short-circuit's
 * spirit exactly (research.md #2). */
@Component({
  selector: 'app-group-join',
  imports: [TranslatePipe],
  templateUrl: './group-join.component.html',
  styleUrl: './group-join.component.scss',
})
export class GroupJoinComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly joinService = inject(GroupJoinService);

  readonly status = signal<Status>('loading');
  readonly errorKey = signal<string | null>(null);

  constructor() {
    const token = this.route.snapshot.paramMap.get('token');
    if (!token) {
      this.status.set('error');
      return;
    }
    this.joinService.resolveJoinLink(token).subscribe({
      next: (preview) => {
        if (preview.already_joined) {
          this.joinService.join(preview.group_id, {}).subscribe({
            next: () => this.status.set('restored'),
            error: (error: ApiError) => {
              this.status.set('error');
              this.errorKey.set(error.i18nKey);
            },
          });
          return;
        }
        if (preview.status === 'disbanded') {
          this.status.set('disbanded');
          return;
        }
        if (preview.current_member_count >= preview.max_members) {
          this.status.set('full');
          return;
        }
        void this.router.navigate(['/groups', preview.group_id, 'join']);
      },
      error: (error: ApiError) => {
        this.status.set('error');
        this.errorKey.set(error.i18nKey);
      },
    });
  }
}
