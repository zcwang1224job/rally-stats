import { Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { GroupListItem } from '../../../core/api/group-join.models';
import { AuthService } from '../../auth/auth.service';
import { GroupAdminService } from '../../group-admin/group-admin.service';
import { GroupJoinService } from '../group-join.service';

@Component({
  selector: 'app-group-list',
  imports: [TranslatePipe, ReactiveFormsModule],
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
  readonly page = signal(1);
  readonly totalPages = signal(1);
  readonly pageNumbers = computed(() =>
    Array.from({ length: this.totalPages() }, (_, i) => i + 1),
  );

  readonly filterForm = this.fb.nonNullable.group({
    court_name: [''],
    court_id: [''],
    time_start: [''],
    time_end: [''],
  });

  constructor() {
    this.load();
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
    const raw = this.filterForm.getRawValue();
    this.joinService
      .listGroups(this.page(), {
        court_name: raw.court_name || undefined,
        court_id: raw.court_id || undefined,
        time_start: raw.time_start || undefined,
        time_end: raw.time_end || undefined,
      })
      .subscribe((response) => {
        this.loading.set(false);
        this.groups.set(response.groups);
        this.totalPages.set(response.total_pages);
      });
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
    return this.joinService.getActiveGuestGroupId() === group.group_id;
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
    const activeGuestGroupId = this.joinService.getActiveGuestGroupId();
    return activeGuestGroupId !== null && activeGuestGroupId !== group.group_id;
  }
}
