import { Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { GroupListItem } from '../../../core/api/group-join.models';
import { AuthService } from '../../auth/auth.service';
import { MatchMode } from '../../group-admin/group-admin.models';
import { GroupAdminService } from '../../group-admin/group-admin.service';
import { GroupJoinService } from '../group-join.service';

type FilterChipKey =
  | 'group_name'
  | 'creator_nickname'
  | 'court_name'
  | 'match_mode'
  | 'time_range';

interface FilterChip {
  key: FilterChipKey;
  labelKey: string;
  value?: string;
  valueKey?: string;
}

@Component({
  selector: 'app-group-list',
  imports: [TranslatePipe, ReactiveFormsModule, RouterLink],
  templateUrl: './group-list.component.html',
  styleUrl: './group-list.component.scss',
})
export class GroupListComponent {
  private readonly joinService = inject(GroupJoinService);
  private readonly groupAdmin = inject(GroupAdminService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly loading = signal(true);
  readonly groups = signal<GroupListItem[]>([]);
  readonly errorKey = signal<string | null>(null);
  readonly page = signal(1);
  readonly totalPages = signal(1);
  readonly pageNumbers = computed(() =>
    Array.from({ length: this.totalPages() }, (_, i) => i + 1),
  );
  /** A handful of placeholder rows shown in place of the group list while
   * the first page loads — purely cosmetic (skeleton screens read as
   * "loading" faster than a bare loading line), no data behind them. */
  readonly skeletonPlaceholders = [1, 2, 3, 4];

  readonly filterForm = this.fb.nonNullable.group({
    court_name: [''],
    time_start: [''],
    time_end: [''],
    group_name: [''],
    creator_nickname: [''],
    match_mode: [''],
  });

  /** Snapshot of the filters a load() call actually used — captured
   * separately from the live filterForm value so the "active filters"
   * chips reflect what the list ON SCREEN was fetched with, not whatever
   * the user has half-typed into the form but not yet submitted. */
  private readonly appliedFilters = signal(this.filterForm.getRawValue());

  private static readonly FILTER_CHIP_LABEL_KEYS: Record<FilterChipKey, string> = {
    group_name: 'groupJoin.groupNameFilter',
    creator_nickname: 'groupJoin.creatorNicknameFilter',
    court_name: 'groupJoin.courtNameFilter',
    match_mode: 'groupJoin.matchModeFilter',
    time_range: 'groupJoin.timeRangeFilter',
  };

  readonly activeFilterChips = computed<FilterChip[]>(() => {
    const filters = this.appliedFilters();
    const chips: FilterChip[] = [];
    for (const key of ['group_name', 'creator_nickname', 'court_name'] as const) {
      const value = filters[key];
      if (value) {
        chips.push({ key, labelKey: GroupListComponent.FILTER_CHIP_LABEL_KEYS[key], value });
      }
    }
    if (filters.match_mode) {
      chips.push({
        key: 'match_mode',
        labelKey: GroupListComponent.FILTER_CHIP_LABEL_KEYS.match_mode,
        valueKey:
          filters.match_mode === 'singles'
            ? 'createGroup.matchModeSingles'
            : 'createGroup.matchModeDoubles',
      });
    }
    if (filters.time_start && filters.time_end) {
      chips.push({
        key: 'time_range',
        labelKey: GroupListComponent.FILTER_CHIP_LABEL_KEYS.time_range,
        value: `${filters.time_start} - ${filters.time_end}`,
      });
    }
    return chips;
  });

  readonly hasActiveFilters = computed(() => this.activeFilterChips().length > 0);

  // Verified once per page visit (not re-checked on every filter/page
  // change — the underlying marker doesn't change from those), rather than
  // reading the raw localStorage marker directly per row — see
  // verifyActiveGuestGroupId()'s docstring for why the raw marker alone
  // can be stale (a since-disbanded group never gets "left"). null both
  // when there's genuinely nothing tracked and before this resolves; the
  // brief window where a row might flash "加入" before flipping to
  // blocked/already-joined is an acceptable trade-off for not spamming an
  // extra request per row.
  private readonly verifiedActiveGuestGroupId = signal<string | null>(null);

  constructor() {
    this.load();
    if (!this.auth.isLoggedIn()) {
      this.joinService
        .verifyActiveGuestGroupId()
        .subscribe((groupId) => this.verifiedActiveGuestGroupId.set(groupId));
    }
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.errorKey.set(null);
    const raw = this.filterForm.getRawValue();
    this.appliedFilters.set(raw);
    this.joinService
      .listGroups(this.page(), {
        court_name: raw.court_name || undefined,
        time_start: raw.time_start || undefined,
        time_end: raw.time_end || undefined,
        group_name: raw.group_name || undefined,
        creator_nickname: raw.creator_nickname || undefined,
        match_mode: (raw.match_mode || undefined) as MatchMode | undefined,
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

  /** Clears one active-filter chip's field(s) and re-applies immediately —
   * a quicker undo than clearing the input and re-submitting the form by
   * hand. `time_range` clears both time fields, since they're shown (and
   * only ever set) as a single combined chip. */
  clearFilter(key: FilterChipKey): void {
    switch (key) {
      case 'time_range':
        this.filterForm.patchValue({ time_start: '', time_end: '' });
        break;
      case 'group_name':
        this.filterForm.patchValue({ group_name: '' });
        break;
      case 'creator_nickname':
        this.filterForm.patchValue({ creator_nickname: '' });
        break;
      case 'court_name':
        this.filterForm.patchValue({ court_name: '' });
        break;
      case 'match_mode':
        this.filterForm.patchValue({ match_mode: '' });
        break;
    }
    this.applyFilters();
  }

  clearAllFilters(): void {
    this.filterForm.reset({
      court_name: '',
      time_start: '',
      time_end: '',
      group_name: '',
      creator_nickname: '',
      match_mode: '',
    });
    this.applyFilters();
  }

  capacityPercent(group: GroupListItem): number {
    if (group.max_members <= 0) {
      return 0;
    }
    return Math.min(100, (group.current_member_count / group.max_members) * 100);
  }

  clickJoin(group: GroupListItem): void {
    // 這個團是自己開的（團長）時，直接換發管理權杖回到管理頁——不需要
    // 密碼、也不需要組團編號＋PIN 重新驗證。
    if (group.created_by_me === true) {
      const token = this.auth.getAccessToken();
      if (token) {
        this.groupAdmin
          .getCreatorAdminToken(group.group_id, { Authorization: `Bearer ${token}` })
          .subscribe((response) => {
            this.groupAdmin.setAdminToken(group.group_id, response.admin_token);
            void this.router.navigate(['/groups', group.group_id, 'admin']);
          });
        return;
      }
    }
    // 已是這個團的成員（登入會員，或——同一瀏覽器——訪客）時，直接進團內
    // 視圖即可——不需要再走一次密碼/暱稱流程，避免已加入者被要求重新輸入
    // 通關密碼。訪客的 member-view 存取本來就是靠這個團自己的
    // guest_session_token（尚未被清除，因為還沒離開），跟會員走 Bearer
    // token 是平行的兩條路徑，member-view 頁面本身兩者都支援。
    if (group.joined_by_me === true || this.isOwnGroupForGuest(group)) {
      void this.router.navigate(['/groups', group.group_id, 'member-view']);
      return;
    }
    // FR-011: front-check before entering the password/nickname flow at all.
    if (group.current_member_count >= group.max_members) {
      return;
    }
    // Front-check for the one-active-group rule — the template already
    // hides the join button for this case, but guard here too in case the
    // list is stale (e.g. joined another group in a different tab since
    // this page loaded). The backend still enforces this regardless for a
    // Member (ALREADY_ACTIVE_IN_ANOTHER_GROUP) if this front-check is ever
    // wrong — for a Guest, this front-check IS the enforcement (see
    // isBlockedElsewhere()'s docstring).
    if (this.isBlockedElsewhere(group)) {
      return;
    }
    void this.router.navigate(['/groups', group.group_id, 'join']);
  }

  isFull(group: GroupListItem): boolean {
    return group.current_member_count >= group.max_members;
  }

  /** `joined_by_me`'s Guest equivalent — the backend never computes that
   * field for an anonymous request (no Member to check against), so a
   * Guest browsing the list otherwise sees a plain "加入" button even for
   * the one group they're already in, as if they'd never joined. Same
   * same-browser-only localStorage marker as isBlockedElsewhere() — the
   * two are mutually exclusive for a given item (this one being true means
   * that one is false, since the tracked group matches this item). */
  isOwnGroupForGuest(group: GroupListItem): boolean {
    if (this.auth.isLoggedIn()) {
      return false;
    }
    return this.verifiedActiveGuestGroupId() === group.group_id;
  }

  /** Backend-computed for a Member (`member_active_elsewhere`, enforced
   * server-side regardless of this check). For a Guest, the backend has no
   * way to know — there's no cross-group identity to check against (see
   * group/service.py `_raise_if_active_elsewhere`'s docstring) — so this
   * falls back to the same-browser-only localStorage marker instead. That
   * marker is a UI nicety only: a different browser, an incognito window,
   * or cleared storage all trivially bypass it, unlike the Member case. */
  isBlockedElsewhere(group: GroupListItem): boolean {
    if (group.member_active_elsewhere === true) {
      return true;
    }
    if (this.auth.isLoggedIn()) {
      return false;
    }
    const activeGuestGroupId = this.verifiedActiveGuestGroupId();
    return activeGuestGroupId !== null && activeGuestGroupId !== group.group_id;
  }
}
