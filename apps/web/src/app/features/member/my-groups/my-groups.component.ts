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

/** The instant a LOCAL calendar day (`<input type="date">`'s `YYYY-MM-DD`)
 * begins, `offsetDays` days later, as an ISO string — or undefined for an
 * empty/unparseable value. Built from the date's parts so it is local
 * midnight (`new Date('YYYY-MM-DD')` would be UTC midnight), which is what
 * makes the filter agree with the local times the list shows: a group
 * opened at 07:30 Taipei time belongs to that day, not to the previous
 * day's UTC date. */
export function localDayStart(date: string, offsetDays = 0): string | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) {
    return undefined;
  }
  const [year, month, day] = match.slice(1).map(Number);
  return new Date(year, month - 1, day + offsetDays).toISOString();
}

/** 我的團 + 忘記管理 PIN 碼 (US7, completes 006-member-friends US4):
 * everything this member has ever created (any status), each with a
 * "忘記管理 PIN 碼" recovery behind a two-step confirm dialog — the reset
 * invalidates the current PIN immediately, so it gets the same
 * Constitution V treatment as disband/regenerate-PIN.
 *
 * Filterable (name / group number / role / opened-between /
 * disbanded-between) and paginated — same filter-panel +
 * `<app-pagination>` convention as the friend list. */
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
    // local calendar days (`YYYY-MM-DD`), both ends inclusive
    created_from: [''],
    created_to: [''],
    disbanded_from: [''],
    disbanded_to: [''],
  });

  /** Snapshot of the filters a load() call actually used — separate from
   * the live filterForm value so "clear filters" only shows once a filter
   * has actually been applied, not just typed (friend-list convention). */
  private readonly appliedFilters = signal(this.filterForm.getRawValue());
  readonly hasActiveFilters = computed(() =>
    Object.values(this.appliedFilters()).some((value) => value !== ''),
  );

  /** Keeps the folded "more filters" section open while one of its filters
   * is applied — an active filter must never be hidden from view. */
  readonly hasAdvancedFilters = computed(() => {
    // everything but the name search lives inside the fold
    return Object.entries(this.appliedFilters()).some(
      ([key, value]) => key !== 'name' && value !== '',
    );
  });

  constructor() {
    this.load();
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  clearFilters(): void {
    this.filterForm.reset();
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
        // The API takes half-open ranges of instants: an inclusive "to" day
        // becomes "before the start of the day after".
        created_from: localDayStart(raw.created_from),
        created_before: localDayStart(raw.created_to, 1),
        disbanded_from: localDayStart(raw.disbanded_from),
        disbanded_before: localDayStart(raw.disbanded_to, 1),
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
