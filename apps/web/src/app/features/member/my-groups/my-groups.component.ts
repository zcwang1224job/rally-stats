import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { MyGroupSummary } from '../../../core/api/friend.models';
import { localDayStart } from '../../../core/local-day';
import { PaginationComponent } from '../../../shared/pagination/pagination.component';
import { ConfirmDialogComponent } from '../../group-admin/shared/confirm-dialog.component';
import { GroupAdminService } from '../../group-admin/group-admin.service';
import { FriendsService } from '../../friends/friends.service';

type RoleFilter = '' | 'creator' | 'member';

/** A match-count bound from a `type="number"` input: a whole number >= 0,
 * or undefined for an empty/invalid field. Unlike a truthiness check, 0 is
 * a real bound ("groups I never played a match in"). */
function toMatchCount(value: string | number | null): number | undefined {
  if (value === null || value === '') {
    return undefined;
  }
  const count = Number(value);
  return Number.isInteger(count) && count >= 0 ? count : undefined;
}

/** 我的團 + 忘記管理 PIN 碼 (US7, completes 006-member-friends US4):
 * everything this member has ever created (any status), each with a
 * "忘記管理 PIN 碼" recovery behind a two-step confirm dialog — the reset
 * invalidates the current PIN immediately, so it gets the same
 * Constitution V treatment as disband/regenerate-PIN.
 *
 * Filterable (name / group number / role / opened-between /
 * disbanded-between / match count) and paginated — same filter-panel +
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
    // my completed matches in the group, both ends inclusive
    match_count_min: [''],
    match_count_max: [''],
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
    const matchCountMin = toMatchCount(raw.match_count_min);
    const matchCountMax = toMatchCount(raw.match_count_max);
    this.appliedFilters.set({
      ...raw,
      name,
      group_number: groupNumber,
      match_count_min: matchCountMin === undefined ? '' : String(matchCountMin),
      match_count_max: matchCountMax === undefined ? '' : String(matchCountMax),
    });
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
        match_count_min: matchCountMin,
        match_count_max: matchCountMax,
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
