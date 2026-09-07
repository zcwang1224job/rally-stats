import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import {
  InvitableFriendsResponse,
  SendGroupInviteResponse,
} from '../../core/api/group-invite.models';
import {
  AdminGroupResponse,
  CreateGroupRequest,
  CreateGroupResponse,
  EditGroupRequest,
  EditScoringSettingsRequest,
  GroupPublic,
  ReauthResponse,
  RegenerateAllCourtsLinkResponse,
  RegenerateJoinLinkResponse,
  RegeneratePinResponse,
} from './group-admin.models';

const SESSION_KEY_PREFIX = 'rally-stats:admin-token:';
const LAST_CREATED_GROUP_KEY = 'rally-stats:last-created-group-id';

/** Centralized API layer for the group-admin feature (T038). Also owns the
 * per-groupId admin_token in sessionStorage so the reauth and admin-page
 * routes share a session without a global auth store. */
@Injectable({ providedIn: 'root' })
export class GroupAdminService {
  private readonly api = inject(ApiClient);

  /** `headers` lets a logged-in Member attach their Bearer token so the
   * backend links the creator's roster entry to their Member identity
   * (`app/domains/group/service.py` `create_group()`) instead of creating a
   * Guest entry — omit it entirely for an anonymous/Guest creation. */
  createGroup(
    payload: CreateGroupRequest,
    headers?: Record<string, string>,
  ): Observable<CreateGroupResponse> {
    return this.api.post<CreateGroupResponse>('/groups', payload, headers);
  }

  reauth(groupNumber: number, adminPin: string): Observable<ReauthResponse> {
    return this.api.post<ReauthResponse>('/groups/reauth', {
      group_number: groupNumber,
      admin_pin: adminPin,
    });
  }

  getAdminView(groupId: string): Observable<AdminGroupResponse> {
    return this.api.get<AdminGroupResponse>(`/groups/${groupId}/admin`, this.authHeader(groupId));
  }

  editGroup(groupId: string, payload: EditGroupRequest): Observable<AdminGroupResponse> {
    return this.api.patch<AdminGroupResponse>(`/groups/${groupId}`, payload, this.authHeader(groupId));
  }

  editScoringSettings(
    groupId: string,
    payload: EditScoringSettingsRequest,
  ): Observable<AdminGroupResponse> {
    return this.api.patch<AdminGroupResponse>(
      `/groups/${groupId}/scoring-settings`,
      payload,
      this.authHeader(groupId),
    );
  }

  disband(groupId: string): Observable<GroupPublic> {
    return this.api.post<GroupPublic>(`/groups/${groupId}/disband`, {}, this.authHeader(groupId));
  }

  regeneratePin(groupId: string): Observable<RegeneratePinResponse> {
    return this.api.post<RegeneratePinResponse>(
      `/groups/${groupId}/regenerate-admin-pin`,
      {},
      this.authHeader(groupId),
    );
  }

  /** "回到我的團" for a logged-in member who created this group — issues a
   * fresh admin token via their Member Bearer token (`memberHeaders`, NOT
   * the per-group admin session `authHeader()` below), no PIN needed and
   * no existing admin session anywhere gets invalidated. */
  getCreatorAdminToken(
    groupId: string,
    memberHeaders: Record<string, string>,
  ): Observable<ReauthResponse> {
    return this.api.post<ReauthResponse>(
      `/groups/${groupId}/creator-admin-token`,
      {},
      memberHeaders,
    );
  }

  regenerateJoinLink(
    groupId: string,
    expectedVersion: number,
  ): Observable<RegenerateJoinLinkResponse> {
    return this.api.post<RegenerateJoinLinkResponse>(
      `/groups/${groupId}/regenerate-join-link`,
      { expected_version: expectedVersion },
      this.authHeader(groupId),
    );
  }

  regenerateAllCourtsLink(
    groupId: string,
    expectedVersion: number,
  ): Observable<RegenerateAllCourtsLinkResponse> {
    return this.api.post<RegenerateAllCourtsLinkResponse>(
      `/groups/${groupId}/regenerate-all-courts-link`,
      { expected_version: expectedVersion },
      this.authHeader(groupId),
    );
  }

  /** 013-group-invite-friends US1/US3: the creator's full friend list, each
   * annotated with its current invite status. */
  listInvitableFriends(groupId: string): Observable<InvitableFriendsResponse> {
    return this.api.get<InvitableFriendsResponse>(
      `/groups/${groupId}/invitable-friends`,
      this.authHeader(groupId),
    );
  }

  sendInvite(groupId: string, inviteeMemberId: string): Observable<SendGroupInviteResponse> {
    return this.api.post<SendGroupInviteResponse>(
      `/groups/${groupId}/invites`,
      { invitee_member_id: inviteeMemberId },
      this.authHeader(groupId),
    );
  }

  private authHeader(groupId: string): Record<string, string> {
    const token = this.getAdminToken(groupId);
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  setAdminToken(groupId: string, token: string): void {
    sessionStorage.setItem(SESSION_KEY_PREFIX + groupId, token);
  }

  getAdminToken(groupId: string): string | null {
    return sessionStorage.getItem(SESSION_KEY_PREFIX + groupId);
  }

  clearAdminToken(groupId: string): void {
    sessionStorage.removeItem(SESSION_KEY_PREFIX + groupId);
    // Keeps the home page's "已經開過團？回到管理頁" shortcut (which links
    // straight to this groupId's admin page) from surviving past the
    // session it points to — a stale link would just bounce back to
    // /groups/reauth anyway (admin-page.component.ts's own 401 handling),
    // but there's no reason to show it at all once we know it's dead.
    if (this.getLastCreatedGroupId() === groupId) {
      sessionStorage.removeItem(LAST_CREATED_GROUP_KEY);
    }
  }

  /** Guest/anonymous group creation (US: home-page "已經開過團？回到管理頁"
   * shortcut) — logged-in members don't need this, they already get a full
   * recovery list via 我的團 (FR-017), so `create-group.component.ts` only
   * calls this for the anonymous-creator path. Session-scoped like the
   * admin token itself (`sessionStorage`, not `localStorage`) — this is a
   * "come back later in the same tab" convenience, not a permanent record. */
  setLastCreatedGroupId(groupId: string): void {
    sessionStorage.setItem(LAST_CREATED_GROUP_KEY, groupId);
  }

  getLastCreatedGroupId(): string | null {
    return sessionStorage.getItem(LAST_CREATED_GROUP_KEY);
  }
}
