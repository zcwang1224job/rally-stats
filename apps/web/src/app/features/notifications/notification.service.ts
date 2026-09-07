import { Injectable, inject, signal } from '@angular/core';
import { Observable, Subscription, tap } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import {
  MarkAllReadResponse,
  MarkNotificationReadResponse,
  NotificationListResponse,
  UnreadCountResponse,
} from '../../core/api/notification.models';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../core/realtime/reconnect-refetch.service';
import { AuthService } from '../auth/auth.service';

/** Centralized notification state (012-realtime-notifications): unread
 * count signal shared by the nav-shell badge and the notification list
 * page, plus the Ably subscription that keeps it live. `init()` is called
 * once (by `nav-shell` while logged in) — a second call is a no-op so
 * re-rendering the nav shell doesn't double-subscribe.
 *
 * On both `notification.created` and reconnect, this always **re-fetches**
 * the unread count from the server rather than optimistically incrementing
 * a local counter (research.md #3) — mirrors constitution III's "reconnect
 * MUST force-overwrite with server state" principle. */
@Injectable({ providedIn: 'root' })
export class NotificationService {
  private readonly api = inject(ApiClient);
  private readonly auth = inject(AuthService);
  private readonly realtime = inject(RealtimeService);
  private readonly reconnectRefetch = inject(ReconnectRefetchService);

  readonly unreadCount = signal(0);

  private initialized = false;
  private subscriptions: Subscription[] = [];

  init(): void {
    if (this.initialized) {
      return;
    }
    this.initialized = true;

    const memberId = this.auth.getCachedMemberId();
    if (memberId) {
      this.subscribeToChannel(memberId);
    } else {
      this.auth.getMe().subscribe((member) => this.subscribeToChannel(member.member_id));
    }

    this.refetchUnreadCount();
    this.subscriptions.push(
      this.reconnectRefetch.onReconnect().subscribe(() => this.refetchUnreadCount()),
    );
  }

  private subscribeToChannel(memberId: string): void {
    this.subscriptions.push(
      this.realtime
        .subscribe(`member:${memberId}:notifications`, 'notification.created')
        .subscribe(() => this.refetchUnreadCount()),
    );
  }

  private refetchUnreadCount(): void {
    this.getUnreadCount().subscribe();
  }

  getUnreadCount(): Observable<UnreadCountResponse> {
    return this.api
      .get<UnreadCountResponse>('/notifications/unread-count', this.authHeader())
      .pipe(tap((response) => this.unreadCount.set(response.unread_count)));
  }

  list(page = 1): Observable<NotificationListResponse> {
    return this.api
      .get<NotificationListResponse>(`/notifications?page=${page}`, this.authHeader())
      .pipe(tap((response) => this.unreadCount.set(response.unread_count)));
  }

  markRead(notificationId: string): Observable<MarkNotificationReadResponse> {
    return this.api
      .post<MarkNotificationReadResponse>(
        `/notifications/${notificationId}/read`,
        {},
        this.authHeader(),
      )
      .pipe(tap(() => this.refetchUnreadCount()));
  }

  markAllRead(): Observable<MarkAllReadResponse> {
    return this.api
      .post<MarkAllReadResponse>('/notifications/read-all', {}, this.authHeader())
      .pipe(tap(() => this.unreadCount.set(0)));
  }

  private authHeader(): Record<string, string> {
    const token = this.auth.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}
