import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { GroupInviteDetailResponse } from '../../../core/api/group-invite.models';
import { GroupInviteService } from '../group-invite.service';

/** US2 (013-group-invite-friends, FR-005~008): the invitee's view/accept/
 * decline screen, reached by clicking a `group_invite` notification. No
 * two-step confirm dialog — accepting/declining an invite is not a
 * data-destroying action (same precedent as friend-request accept/reject). */
@Component({
  selector: 'app-group-invite-detail',
  imports: [TranslatePipe, RouterLink],
  templateUrl: './group-invite-detail.component.html',
  styleUrl: './group-invite-detail.component.scss',
})
export class GroupInviteDetailComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly groupInvite = inject(GroupInviteService);

  private readonly inviteId = this.route.snapshot.paramMap.get('inviteId')!;

  readonly detail = signal<GroupInviteDetailResponse | null>(null);
  readonly loading = signal(true);
  readonly errorKey = signal<string | null>(null);
  readonly actionErrorKey = signal<string | null>(null);

  constructor() {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.groupInvite.getDetail(this.inviteId).subscribe({
      next: (detail) => {
        this.loading.set(false);
        this.detail.set(detail);
      },
      error: (error: ApiError) => {
        this.loading.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  accept(): void {
    this.actionErrorKey.set(null);
    this.groupInvite.accept(this.inviteId).subscribe({
      next: (response) => {
        void this.router.navigate(['/groups', response.group_id, 'member-view']);
      },
      error: (error: ApiError) => {
        this.actionErrorKey.set(error.i18nKey);
        // FR-013: a GROUP_FULL failure leaves the invite pending — no need
        // to reload. Every other failure (already-active-elsewhere,
        // disbanded, not-pending) reflects a real status change, so refresh
        // the detail to show it.
        if (error.errorCode !== 'GROUP_FULL') {
          this.load();
        }
      },
    });
  }

  decline(): void {
    this.actionErrorKey.set(null);
    this.groupInvite.decline(this.inviteId).subscribe({
      next: () => this.load(),
      error: (error: ApiError) => this.actionErrorKey.set(error.i18nKey),
    });
  }
}
