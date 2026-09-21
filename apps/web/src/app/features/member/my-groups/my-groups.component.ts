import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { MyGroupSummary } from '../../../core/api/friend.models';
import { PaginationComponent } from '../../../shared/pagination/pagination.component';
import { ConfirmDialogComponent } from '../../group-admin/shared/confirm-dialog.component';
import { GroupAdminService } from '../../group-admin/group-admin.service';
import { FriendsService } from '../../friends/friends.service';

type RoleFilter = '' | 'creator' | 'member';
type StatusFilter = '' | 'active' | 'disbanded';

/** 我的團 + 忘記管理 PIN 碼 (US7, completes 006-member-friends US4):
 * everything this member has ever created (any status), each with a
 * "忘記管理 PIN 碼" recovery behind a two-step confirm dialog — the reset
 * invalidates the current PIN immediately, so it gets the same
 * Constitution V treatment as disband/regenerate-PIN.
 *
 * Filterable (name / group number / role / group status) and paginated —
 * same filter-panel + `<app-pagination>` convention as the friend list. */
@Component({
  selector: 'app-my-groups',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    ConfirmDialogComponent,
    DatePipe,
    PaginationComponent,
  ],
  templateUrl: './my-groups.component.html',
  styleUrl: './my-groups.component.scss',
})
export class MyGroupsComponent {
  private readonly fb = inject(FormBuilder);
  private readonly friends = inject(FriendsService);
  private readonly groupAdmin = inject(GroupAdminService);
  private readonly router = inject(Router);

  private readonly dialog = viewChild.required<ConfirmDialogComponent>('forgotPinDialog');

  readonly loading = signal(true);
  readonly groups = signal<MyGroupSummary[]>([]);
  readonly page = signal(1);
  readonly totalPages = signal(1);
  readonly errorKey = signal<string | null>(null);
  readonly forgotPinTarget = signal<MyGroupSummary | null>(null);

  readonly filterForm = this.fb.nonNullable.group({
    name: [''],
    group_number: [''],
    role: ['' as RoleFilter],
    status: ['' as StatusFilter],
  });

  /** Snapshot of the filters a load() call actually used — separate from
   * the live filterForm value so "clear filters" only shows once a filter
   * has actually been applied, not just typed (friend-list convention). */
  private readonly appliedFilters = signal(this.filterForm.getRawValue());
  readonly hasActiveFilters = computed(() =>
    Object.values(this.appliedFilters()).some((value) => value !== ''),
  );

  constructor() {
    this.load();
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  clearFilters(): void {
    this.filterForm.reset({ name: '', group_number: '', role: '', status: '' });
    this.applyFilters();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.errorKey.set(null);
    const raw = this.filterForm.getRawValue();
    const name = raw.name.trim();
    const groupNumber = raw.group_number.trim();
    this.appliedFilters.set({ ...raw, name, group_number: groupNumber });
    this.friends
      .getMyGroups(this.page(), {
        name: name || undefined,
        group_number: groupNumber || undefined,
        role: raw.role || undefined,
        status: raw.status || undefined,
      })
      .subscribe({
        next: (response) => {
          this.loading.set(false);
          this.groups.set(response.groups);
          this.totalPages.set(response.total_pages);
        },
        error: (error: ApiError) => {
          this.loading.set(false);
          this.errorKey.set(error.i18nKey);
        },
      });
  }

  openGroupHistory(group: MyGroupSummary): void {
    void this.router.navigate(['/member/my-groups', group.group_id]);
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
