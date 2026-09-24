import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { MyGroupSummary } from '../../../core/api/friend.models';
import { localDayStart } from '../../../core/local-day';
import { PaginationComponent } from '../../../shared/pagination/pagination.component';
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

/** 我的團 (US7): everything this member has ever created or joined (any
 * status). A group the member created and hasn't disbanded gets a
 * 「進入管理」button that goes straight to the admin page on the member's
 * own login — no PIN, and unlike the old 忘記 PIN reset it leaves the
 * current PIN and every other admin session untouched.
 *
 * Filterable (name / group number / role / opened-between /
 * disbanded-between / match count) and paginated — same filter-panel +
 * `<app-pagination>` convention as the friend list. */
@Component({
  selector: 'app-my-groups',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
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

  readonly loading = signal(true);
  readonly groups = signal<MyGroupSummary[]>([]);
  readonly page = signal(1);
  readonly totalPages = signal(1);
  readonly errorKey = signal<string | null>(null);
  readonly enteringAdminGroupId = signal<string | null>(null);

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

  enterAdmin(group: MyGroupSummary): void {
    this.errorKey.set(null);
    this.enteringAdminGroupId.set(group.group_id);
    this.groupAdmin.recoverCreatorAdminToken(group.group_id).subscribe((recovered) => {
      this.enteringAdminGroupId.set(null);
      if (recovered) {
        void this.router.navigate(['/groups', group.group_id, 'admin']);
      } else {
        this.errorKey.set('myGroups.enterAdminFailed');
      }
    });
  }
}
