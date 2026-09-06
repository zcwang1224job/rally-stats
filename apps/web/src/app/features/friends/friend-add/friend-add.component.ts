import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { SearchMemberResponse } from '../../../core/api/friend.models';
import { FriendsService } from '../friends.service';

/** 新增好友 (US7) — search by user_number, then act on the returned
 * four-state `friendship_status` per contracts/friends-frontend-contract.md
 * row 1-3. */
@Component({
  selector: 'app-friend-add',
  imports: [ReactiveFormsModule, RouterLink, TranslatePipe],
  templateUrl: './friend-add.component.html',
  styleUrl: './friend-add.component.scss',
})
export class FriendAddComponent {
  private readonly fb = inject(FormBuilder);
  private readonly friends = inject(FriendsService);

  readonly form = this.fb.nonNullable.group({
    user_number: ['', Validators.required],
  });

  readonly result = signal<SearchMemberResponse | null>(null);
  readonly errorKey = signal<string | null>(null);
  readonly sent = signal(false);

  search(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.errorKey.set(null);
    this.result.set(null);
    this.sent.set(false);
    this.friends.searchMember(this.form.getRawValue().user_number).subscribe({
      next: (response) => this.result.set(response),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  sendRequest(): void {
    const target = this.result();
    if (!target) {
      return;
    }
    this.errorKey.set(null);
    this.friends.sendFriendRequest(target.user_number).subscribe({
      next: () => {
        this.sent.set(true);
        this.result.set({ ...target, friendship_status: 'pending_outgoing' });
      },
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }
}
