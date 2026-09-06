import { Injectable, inject } from '@angular/core';
import { Observable, catchError, map, of, tap } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import {
  GroupListResponse,
  GuestSessionResponse,
  JoinGroupRequest,
  JoinGroupResponse,
  JoinLinkPreviewResponse,
  VerifyPasswordResponse,
} from '../../core/api/group-join.models';
import { GroupPublic, MatchMode } from '../group-admin/group-admin.models';
import { AuthService } from '../auth/auth.service';

const GUEST_TOKEN_KEY_PREFIX = 'rally-stats:guest-session-token:';
const ACTIVE_GUEST_GROUP_KEY = 'rally-stats:guest-active-group-id';

export interface GroupListFilters {
  court_name?: string;
  court_id?: string;
  time_start?: string;
  time_end?: string;
  group_name?: string;
  creator_nickname?: string;
  match_mode?: MatchMode;
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
    if (filters.group_name) {
      params.set('group_name', filters.group_name);
    }
    if (filters.creator_nickname) {
      params.set('creator_nickname', filters.creator_nickname);
    }
    if (filters.match_mode) {
      params.set('match_mode', filters.match_mode);
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
            // A guest_session_token only ever comes back for a Guest join
            // (a Member's is always null) — this is the one place every
            // Guest join path funnels through, so it's the right spot to
            // record "this browser is now active in this group" too.
            this.setActiveGuestGroupId(groupId);
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

  /** Best-effort, same-browser-only tracking of "which group is this
   * Guest currently active in" — deliberately separate from the per-group
   * guest_session_token above (that's scoped to resuming ONE group's
   * session on reload, and today is never cleared on leaving it, so it
   * isn't a reliable "currently active" signal by itself). This can't
   * enforce the one-active-group rule the way the backend does for
   * Members (a different browser, incognito window, or cleared storage
   * trivially bypasses it) — it's a UI nicety for the common case of the
   * same guest, same browser, forgetting they're already in a group. */
  setActiveGuestGroupId(groupId: string): void {
    localStorage.setItem(ACTIVE_GUEST_GROUP_KEY, groupId);
  }

  getActiveGuestGroupId(): string | null {
    return localStorage.getItem(ACTIVE_GUEST_GROUP_KEY);
  }

  clearActiveGuestGroupId(): void {
    localStorage.removeItem(ACTIVE_GUEST_GROUP_KEY);
  }

  /** The raw marker alone isn't enough to safely block on: disbanding a
   * group (manually, or via the inactivity auto-disband scheduler)
   * deliberately never touches its RosterEntries (a disbanded group stays
   * readable/leavable — same reason group/service.py's
   * get_active_group_id_for_member() has to filter out disbanded groups
   * on the Member side), and being kicked doesn't clear this marker either
   * (only a voluntary leave does, in leave-group.component.ts) — nothing
   * else would ever clear this marker in either case. Verifies against the
   * live group before reporting it as still blocking, clearing the marker
   * if it's stale so a Guest isn't permanently locked out.
   *
   * Prefers resolveGuestSession() (by this group's guest_session_token)
   * when one is on file — it checks this Guest's own RosterEntry.status,
   * so it catches "kicked from a still-active group" as well as
   * "disbanded", the same way get_active_group_id_for_member() does for a
   * Member. Falls back to a plain group-status check (disbanded-only) when
   * no token is on file for this group — there's no Guest identity to
   * resolve against in that case. */
  verifyActiveGuestGroupId(): Observable<string | null> {
    const groupId = this.getActiveGuestGroupId();
    if (groupId === null) {
      return of(null);
    }
    const guestToken = this.getGuestSessionToken(groupId);
    if (guestToken !== null) {
      return this.resolveGuestSession(guestToken).pipe(
        map(() => groupId),
        catchError(() => {
          this.clearActiveGuestGroupId();
          this.clearGuestSessionToken(groupId);
          return of(null);
        }),
      );
    }
    return this.api.get<GroupPublic>(`/groups/${groupId}`).pipe(
      map((group) => {
        if (group.status === 'disbanded') {
          this.clearActiveGuestGroupId();
          return null;
        }
        return groupId;
      }),
      catchError(() => {
        this.clearActiveGuestGroupId();
        return of(null);
      }),
    );
  }

  private authHeader(): Record<string, string> {
    const token = this.auth.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}
