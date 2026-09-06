import { Injectable, inject } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import {
  GroupListResponse,
  GuestSessionResponse,
  JoinGroupRequest,
  JoinGroupResponse,
  JoinLinkPreviewResponse,
  VerifyPasswordResponse,
} from '../../core/api/group-join.models';
import { AuthService } from '../auth/auth.service';

const GUEST_TOKEN_KEY_PREFIX = 'rally-stats:guest-session-token:';

export interface GroupListFilters {
  court_name?: string;
  court_id?: string;
  time_start?: string;
  time_end?: string;
}

/** Centralized API layer for the join-group feature (004). Also owns
 * per-groupId Guest Session Token storage in localStorage (US4) — a Guest's
 * identity for one group, parallel to how group-admin owns admin_token. */
@Injectable({ providedIn: 'root' })
export class GroupJoinService {
  private readonly api = inject(ApiClient);
  private readonly auth = inject(AuthService);

  listGroups(page = 1, filters: GroupListFilters = {}): Observable<GroupListResponse> {
    const params = new URLSearchParams({ page: String(page) });
    if (filters.court_name) {
      params.set('court_name', filters.court_name);
    }
    if (filters.court_id) {
      params.set('court_id', filters.court_id);
    }
    if (filters.time_start && filters.time_end) {
      params.set('time_start', filters.time_start);
      params.set('time_end', filters.time_end);
    }
    return this.api.get<GroupListResponse>(`/groups?${params.toString()}`, this.authHeader());
  }

  resolveJoinLink(token: string): Observable<JoinLinkPreviewResponse> {
    return this.api.get<JoinLinkPreviewResponse>(`/join/${token}`, this.authHeader());
  }

  verifyPassword(groupId: string, password: string): Observable<VerifyPasswordResponse> {
    return this.api.post<VerifyPasswordResponse>(`/groups/${groupId}/verify-password`, {
      password,
    });
  }

  join(groupId: string, payload: JoinGroupRequest): Observable<JoinGroupResponse> {
    return this.api
      .post<JoinGroupResponse>(`/groups/${groupId}/join`, payload, this.authHeader())
      .pipe(
        tap((response) => {
          if (response.guest_session_token) {
            this.setGuestSessionToken(groupId, response.guest_session_token);
          }
        }),
      );
  }

  resolveGuestSession(token: string): Observable<GuestSessionResponse> {
    return this.api.get<GuestSessionResponse>(`/groups/by-guest-token/${token}`);
  }

  setGuestSessionToken(groupId: string, token: string): void {
    localStorage.setItem(GUEST_TOKEN_KEY_PREFIX + groupId, token);
  }

  getGuestSessionToken(groupId: string): string | null {
    return localStorage.getItem(GUEST_TOKEN_KEY_PREFIX + groupId);
  }

  clearGuestSessionToken(groupId: string): void {
    localStorage.removeItem(GUEST_TOKEN_KEY_PREFIX + groupId);
  }

  private authHeader(): Record<string, string> {
    const token = this.auth.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}
