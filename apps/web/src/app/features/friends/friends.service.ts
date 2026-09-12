import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import {
  FriendListResponse,
  FriendRequestResponse,
  ForgotAdminPinResponse,
  IncomingFriendRequestsResponse,
  MemberGroupHistoryFilters,
  MemberGroupHistoryResponse,
  MyGroupsResponse,
  SearchMemberResponse,
} from '../../core/api/friend.models';
import { AuthService } from '../auth/auth.service';

/** API layer for the friends system + "my groups"/forgot-admin-PIN recovery
 * (US7, 010-app-wide-ui-redesign) — completes the already-approved
 * 006-member-friends spec; every endpoint here already existed as a
 * contract before this feature, just unimplemented (see
 * specs/010-app-wide-ui-redesign/contracts/reused-api-contracts.md). */
@Injectable({ providedIn: 'root' })
export class FriendsService {
  private readonly api = inject(ApiClient);
  private readonly auth = inject(AuthService);

  searchMember(userNumber: string): Observable<SearchMemberResponse> {
    const params = new URLSearchParams({ user_number: userNumber });
    return this.api.get<SearchMemberResponse>(
      `/members/search?${params.toString()}`,
      this.authHeader(),
    );
  }

  sendFriendRequest(addresseeUserNumber: string): Observable<FriendRequestResponse> {
    return this.api.post<FriendRequestResponse>(
      '/friends/requests',
      { addressee_user_number: addresseeUserNumber },
      this.authHeader(),
    );
  }

  listFriends(
    page = 1,
    filters: { nickname?: string; user_number?: string } = {},
  ): Observable<FriendListResponse> {
    const params = new URLSearchParams({ page: String(page) });
    if (filters.nickname) {
      params.set('nickname', filters.nickname);
    }
    if (filters.user_number) {
      params.set('user_number', filters.user_number);
    }
    return this.api.get<FriendListResponse>(`/friends?${params.toString()}`, this.authHeader());
  }

  listIncomingRequests(): Observable<IncomingFriendRequestsResponse> {
    return this.api.get<IncomingFriendRequestsResponse>(
      '/friends/requests/incoming',
      this.authHeader(),
    );
  }

  acceptFriendRequest(friendRequestId: string): Observable<FriendRequestResponse> {
    return this.api.post<FriendRequestResponse>(
      `/friends/requests/${friendRequestId}/accept`,
      {},
      this.authHeader(),
    );
  }

  rejectFriendRequest(friendRequestId: string): Observable<FriendRequestResponse> {
    return this.api.post<FriendRequestResponse>(
      `/friends/requests/${friendRequestId}/reject`,
      {},
      this.authHeader(),
    );
  }

  unfriend(friendRequestId: string): Observable<FriendRequestResponse> {
    return this.api.delete<FriendRequestResponse>(
      `/friends/${friendRequestId}`,
      this.authHeader(),
    );
  }

  getMyGroups(): Observable<MyGroupsResponse> {
    return this.api.get<MyGroupsResponse>('/members/me/groups', this.authHeader());
  }

  /** 014-member-groups-history: the group's own shared match history
   * (every completed match, any participant) — works even after leaving
   * or being kicked (FR-006) — plus this member's own personal stats
   * within that group. `nickname` searches either team across the WHOLE
   * group's matches, not just the caller's own games (FR-009). */
  getMemberGroupHistory(
    groupId: string,
    page = 1,
    filters: MemberGroupHistoryFilters = {},
  ): Observable<MemberGroupHistoryResponse> {
    const params = new URLSearchParams({ page: String(page) });
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') {
        params.set(key, String(value));
      }
    }
    return this.api.get<MemberGroupHistoryResponse>(
      `/members/me/groups/${groupId}/history?${params.toString()}`,
      this.authHeader(),
    );
  }

  forgotAdminPin(groupId: string): Observable<ForgotAdminPinResponse> {
    return this.api.post<ForgotAdminPinResponse>(
      `/groups/${groupId}/forgot-admin-pin`,
      {},
      this.authHeader(),
    );
  }

  private authHeader(): Record<string, string> {
    const token = this.auth.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}
