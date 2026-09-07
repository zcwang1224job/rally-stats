import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { FriendSummary } from '../../../core/api/friend.models';
import { ConfirmDialogComponent } from '../../group-admin/shared/confirm-dialog.component';
import { FriendsService } from '../friends.service';

/** 好友列表 (US7): filter, paginate, unfriend behind a two-step confirm
 * dialog (Constitution V) — mirrors admin-page's kick-member pattern
 * (one shared dialog + a "target" signal, not one dialog per row). */
@Component({
  selector: 'app-friend-list',
  imports: [ReactiveFormsModule, RouterLink, TranslatePipe, ConfirmDialogComponent],
  templateUrl: './friend-list.component.html',
  styleUrl: './friend-list.component.scss',
})
export class FriendListComponent {
  private readonly fb = inject(FormBuilder);
  private readonly friends = inject(FriendsService);

  private readonly dialog = viewChild.required<ConfirmDialogComponent>('unfriendDialog');

  readonly loading = signal(true);
  readonly items = signal<FriendSummary[]>([]);
  readonly page = signal(1);
  readonly totalPages = signal(1);
  readonly pageNumbers = computed(() =>
    Array.from({ length: this.totalPages() }, (_, i) => i + 1),
  );
  readonly errorKey = signal<string | null>(null);
  readonly unfriendTarget = signal<FriendSummary | null>(null);

  readonly filterForm = this.fb.nonNullable.group({
    nickname: [''],
    user_number: [''],
  });

  /** Snapshot of the filters a load() call actually used — separate from
   * the live filterForm value so "clear filters" only shows once a filter
   * has actually been applied, not just typed (matches the group-list /
   * match-history filter panel convention). */
  private readonly appliedFilters = signal(this.filterForm.getRawValue());
  readonly hasActiveFilters = computed(
    () => !!(this.appliedFilters().nickname || this.appliedFilters().user_number),
  );

  constructor() {
    this.load();
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  clearFilters(): void {
    this.filterForm.reset({ nickname: '', user_number: '' });
    this.applyFilters();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    const raw = this.filterForm.getRawValue();
    this.appliedFilters.set(raw);
    this.friends
      .listFriends(this.page(), {
        nickname: raw.nickname || undefined,
        user_number: raw.user_number || undefined,
      })
      .subscribe((response) => {
        this.loading.set(false);
        this.items.set(response.friends);
        this.totalPages.set(response.total_pages);
      });
  }

  openUnfriendDialog(friend: FriendSummary): void {
    this.unfriendTarget.set(friend);
    this.errorKey.set(null);
    this.dialog().open();
  }

  confirmUnfriend(): void {
    const target = this.unfriendTarget();
    if (!target) {
      return;
    }
    if (!target.friend_request_id) {
      return;
    }
    this.friends.unfriend(target.friend_request_id).subscribe({
      next: () => this.load(),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }
}
