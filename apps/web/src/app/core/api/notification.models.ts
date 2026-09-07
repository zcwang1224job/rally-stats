// Mirrors apps/api/app/domains/notification/schemas.py — see
// specs/012-realtime-notifications/contracts/notification-api.md.

import { FriendSummary } from './friend.models';

export type NotificationType = 'friend_request';

export interface FriendRequestNotificationDetail {
  friend_request_id: string;
  status: 'pending' | 'accepted' | 'rejected' | 'unfriended';
  requester: FriendSummary;
}

export interface NotificationSummary {
  notification_id: string;
  type: NotificationType;
  read: boolean;
  created_at: string;
  /** Populated when `type === 'friend_request'` (today, always). A future
   * notification type adds its own nullable field alongside this one. */
  friend_request: FriendRequestNotificationDetail | null;
}

export interface NotificationListResponse {
  notifications: NotificationSummary[];
  unread_count: number;
  page: number;
  total_pages: number;
}

export interface UnreadCountResponse {
  unread_count: number;
}

export interface MarkNotificationReadResponse {
  notification_id: string;
  read: boolean;
}

export interface MarkAllReadResponse {
  marked_count: number;
}
