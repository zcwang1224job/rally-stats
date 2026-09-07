// Mirrors apps/api/app/domains/notification/schemas.py — see
// specs/012-realtime-notifications/contracts/notification-api.md.

import { FriendSummary } from './friend.models';
import { GroupInviteStatus } from './group-invite.models';

export type NotificationType = 'friend_request' | 'group_invite' | 'group_invite_capacity_full';

export interface FriendRequestNotificationDetail {
  friend_request_id: string;
  status: 'pending' | 'accepted' | 'rejected' | 'unfriended';
  requester: FriendSummary;
}

/** 013-group-invite-friends: shared shape for both `"group_invite"`
 * (delivered to the invitee) and `"group_invite_capacity_full"` (delivered
 * to the inviter) — same underlying invite, rendered from either
 * perspective. */
export interface GroupInviteNotificationDetail {
  invite_id: string;
  group_id: string;
  group_name: string;
  status: GroupInviteStatus;
  inviter: FriendSummary;
  invitee: FriendSummary;
}

export interface NotificationSummary {
  notification_id: string;
  type: NotificationType;
  read: boolean;
  created_at: string;
  /** Populated when `type === 'friend_request'`. A future notification type
   * adds its own nullable field alongside this one rather than replacing
   * it. */
  friend_request: FriendRequestNotificationDetail | null;
  /** Populated when `type` is `"group_invite"` or
   * `"group_invite_capacity_full"`. */
  group_invite: GroupInviteNotificationDetail | null;
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
