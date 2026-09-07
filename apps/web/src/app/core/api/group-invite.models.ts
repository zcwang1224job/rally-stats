// Mirrors apps/api/app/domains/group_invite/schemas.py — see
// specs/013-group-invite-friends/contracts/group-invite-api.md.

export type GroupInviteStatus = 'pending' | 'accepted' | 'declined' | 'invalidated';
export type InviteStatusForFriend = GroupInviteStatus | 'not_invited' | 'already_member';

export interface InvitableFriendSummary {
  member_id: string;
  nickname: string | null;
  user_number: string;
  invite_status: InviteStatusForFriend;
  invite_id: string | null;
}

export interface InvitableFriendsResponse {
  friends: InvitableFriendSummary[];
}

export interface SendGroupInviteResponse {
  invite_id: string;
  status: GroupInviteStatus;
}

export interface GroupInviteDetailResponse {
  invite_id: string;
  status: GroupInviteStatus;
  group_id: string;
  group_name: string;
  inviter_nickname: string | null;
}

export interface AcceptGroupInviteResponse {
  group_id: string;
  roster_entry_id: string;
  nickname: string;
}

export interface DeclineGroupInviteResponse {
  invite_id: string;
  status: 'declined';
}
