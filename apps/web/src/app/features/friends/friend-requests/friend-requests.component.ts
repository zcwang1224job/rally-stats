import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { IncomingFriendRequest } from '../../../core/api/friend.models';
import { FriendsService } from '../friends.service';

/** 回覆好友申請 (US7): incoming pending requests, 接受/拒絕. No two-step
 * confirm dialog here — unlike unfriend/forgot-PIN, accepting or rejecting
 * an incoming request is not a data-destroying action (Constitution V only
 * requires confirmation for destructive/irreversible operations). */
@Component({
  selector: 'app-friend-requests',
  imports: [RouterLink, TranslatePipe],
  templateUrl: './friend-requests.component.html',
  styleUrl: './friend-requests.component.scss',
})
export class FriendRequestsComponent {
  private readonly friends = inject(FriendsService);

  readonly loading = signal(true);
  readonly items = signal<IncomingFriendRequest[]>([]);
  readonly errorKey = signal<string | null>(null);

  constructor() {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.friends.listIncomingRequests().subscribe((response) => {
      this.loading.set(false);
      this.items.set(response.requests);
    });
  }

  accept(request: IncomingFriendRequest): void {
    this.errorKey.set(null);
    this.friends.acceptFriendRequest(request.friend_request_id).subscribe({
      next: () => this.load(),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  reject(request: IncomingFriendRequest): void {
    this.errorKey.set(null);
    this.friends.rejectFriendRequest(request.friend_request_id).subscribe({
      next: () => this.load(),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }
}
