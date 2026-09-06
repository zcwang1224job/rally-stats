import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import {
  GroupMatchRecordsResponse,
  GroupStandingsResponse,
  LeaveGroupResponse,
} from '../../core/api/group-member-view.models';
import { ScheduleResponse } from '../group-admin/schedule-management/schedule.models';
import { AuthService } from '../auth/auth.service';
import { GroupJoinService } from '../group-join/group-join.service';

/** Centralized API layer for the non-admin member view (005): 賽程/戰績/
 * 對戰紀錄/退出組團. Every endpoint here is gated by
 * `resolve_active_roster_membership()` (Guest token OR Member Bearer
 * token) — reuses GroupJoinService's per-group Guest token storage and
 * AuthService's member access token rather than owning a third identity
 * store. */
@Injectable({ providedIn: 'root' })
export class GroupMemberViewService {
  private readonly api = inject(ApiClient);
  private readonly auth = inject(AuthService);
  private readonly groupJoin = inject(GroupJoinService);

  getMemberSchedule(groupId: string): Observable<ScheduleResponse> {
    return this.api.get<ScheduleResponse>(
      `/groups/${groupId}/member-schedule${this.guestTokenQuery(groupId)}`,
      this.authHeader(),
    );
  }

  getStandings(groupId: string): Observable<GroupStandingsResponse> {
    return this.api.get<GroupStandingsResponse>(
      `/groups/${groupId}/standings${this.guestTokenQuery(groupId)}`,
      this.authHeader(),
    );
  }

  getMatchRecords(groupId: string, page = 1): Observable<GroupMatchRecordsResponse> {
    const separator = this.guestTokenQuery(groupId) ? '&' : '?';
    return this.api.get<GroupMatchRecordsResponse>(
      `/groups/${groupId}/match-records${this.guestTokenQuery(groupId)}${separator}page=${page}`,
      this.authHeader(),
    );
  }

  /** The leave-group endpoint needs the caller's own `roster_entry_id`,
   * which nothing on this route otherwise surfaces. A logged-in Member
   * always takes priority over any leftover per-group Guest token in
   * localStorage — someone who joined as Guest and later registered/
   * logged in and rejoined the same group as a Member must resolve to
   * their current Member entry, not a stale Guest one nothing ever clears.
   * Member: re-`join()` idempotently — an already-active member's roster
   * entry short-circuits the join write path (FR-020a) *before* the
   * disbanded/password/capacity checks (group/service.py `join_group`),
   * so this is a safe, side-effect-free way to read back the ID with no
   * new backend endpoint. Guest: 004's existing `resolveGuestSession()`
   * returns it directly. */
  resolveRosterEntryId(groupId: string): Observable<string> {
    if (this.auth.isLoggedIn()) {
      return this.groupJoin
        .join(groupId, { password: null, nickname: null })
        .pipe(map((response) => response.roster_entry_id));
    }
    const guestToken = this.groupJoin.getGuestSessionToken(groupId);
    return this.groupJoin
      .resolveGuestSession(guestToken ?? '')
      .pipe(map((session) => session.roster_entry_id));
  }

  leaveGroup(groupId: string, rosterEntryId: string): Observable<LeaveGroupResponse> {
    // Same Member-over-Guest priority as resolveRosterEntryId() — the
    // backend trusts guest_session_token over the Bearer identity when
    // both are present (research.md #5), so a logged-in Member's request
    // MUST NOT carry a stale per-group Guest token.
    const guestToken = this.auth.isLoggedIn() ? null : this.groupJoin.getGuestSessionToken(groupId);
    return this.api.post<LeaveGroupResponse>(
      `/groups/${groupId}/roster/${rosterEntryId}/leave`,
      { guest_session_token: guestToken },
      this.authHeader(),
    );
  }

  private guestTokenQuery(groupId: string): string {
    const token = this.groupJoin.getGuestSessionToken(groupId);
    return token ? `?guest_session_token=${encodeURIComponent(token)}` : '';
  }

  private authHeader(): Record<string, string> {
    const token = this.auth.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}
