import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
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
  }
}
