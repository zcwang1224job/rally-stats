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
    // 已是這個團的成員（登入會員）時，直接進團內視圖即可——不需要再走一次
    // 密碼/暱稱流程，避免已加入者被要求重新輸入通關密碼。
    if (group.joined_by_me === true) {
      void this.router.navigate(['/groups', group.group_id, 'member-view']);
      return;
    }
    // FR-011: front-check before entering the password/nickname flow at all.
    if (group.current_member_count >= group.max_members) {
      return;
    }
    void this.router.navigate(['/groups', group.group_id, 'join']);
  }

  isFull(group: GroupListItem): boolean {
    return group.current_member_count >= group.max_members;
  }
}
