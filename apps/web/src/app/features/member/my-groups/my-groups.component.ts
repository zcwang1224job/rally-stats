import { Component, inject, signal, viewChild } from '@angular/core';
import { Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { MyGroupSummary } from '../../../core/api/friend.models';
import { ConfirmDialogComponent } from '../../group-admin/shared/confirm-dialog.component';
import { GroupAdminService } from '../../group-admin/group-admin.service';
import { FriendsService } from '../../friends/friends.service';

/** 我的團 + 忘記管理 PIN 碼 (US7, completes 006-member-friends US4):
 * everything this member has ever created (any status), each with a
 * "忘記管理 PIN 碼" recovery behind a two-step confirm dialog — the reset
 * invalidates the current PIN immediately, so it gets the same
 * Constitution V treatment as disband/regenerate-PIN. */
@Component({
  selector: 'app-my-groups',
  imports: [TranslatePipe, ConfirmDialogComponent],
  templateUrl: './my-groups.component.html',
  styleUrl: './my-groups.component.scss',
})
export class MyGroupsComponent {
  private readonly friends = inject(FriendsService);
  private readonly groupAdmin = inject(GroupAdminService);
  private readonly router = inject(Router);

  private readonly dialog = viewChild.required<ConfirmDialogComponent>('forgotPinDialog');

  readonly loading = signal(true);
  readonly groups = signal<MyGroupSummary[]>([]);
  readonly errorKey = signal<string | null>(null);
  readonly forgotPinTarget = signal<MyGroupSummary | null>(null);

  constructor() {
    this.friends.getMyGroups().subscribe((response) => {
      this.loading.set(false);
      this.groups.set(response.groups);
    });
  }

  openForgotPinDialog(group: MyGroupSummary): void {
    this.forgotPinTarget.set(group);
    this.errorKey.set(null);
    this.dialog().open();
  }

  confirmForgotPin(): void {
    const target = this.forgotPinTarget();
    if (!target) {
      return;
    }
    this.friends.forgotAdminPin(target.group_id).subscribe({
      next: (response) => {
        this.groupAdmin.setAdminToken(target.group_id, response.admin_token);
        void this.router.navigate(['/groups', target.group_id, 'admin']);
      },
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }
}
