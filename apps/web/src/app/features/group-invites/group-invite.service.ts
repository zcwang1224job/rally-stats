import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import {
  AcceptGroupInviteResponse,
  DeclineGroupInviteResponse,
  GroupInviteDetailResponse,
} from '../../core/api/group-invite.models';
import { AuthService } from '../auth/auth.service';

/** API layer for the invitee-facing side of 013-group-invite-friends
 * (`GET/POST /group-invites/...`, `require_verified_member`). The
 * creator-facing side (`/groups/{id}/invitable-friends`, `/invites`) lives
 * on `GroupAdminService` instead, since it's authorized by the group's own
 * admin_token, not the caller's Member Bearer token. */
@Injectable({ providedIn: 'root' })
export class GroupInviteService {
  private readonly api = inject(ApiClient);
  private readonly auth = inject(AuthService);

  getDetail(inviteId: string): Observable<GroupInviteDetailResponse> {
    return this.api.get<GroupInviteDetailResponse>(
      `/group-invites/${inviteId}`,
      this.authHeader(),
    );
  }

  accept(inviteId: string): Observable<AcceptGroupInviteResponse> {
    return this.api.post<AcceptGroupInviteResponse>(
      `/group-invites/${inviteId}/accept`,
      {},
      this.authHeader(),
    );
  }

  decline(inviteId: string): Observable<DeclineGroupInviteResponse> {
    return this.api.post<DeclineGroupInviteResponse>(
      `/group-invites/${inviteId}/decline`,
      {},
      this.authHeader(),
    );
  }

  private authHeader(): Record<string, string> {
    const token = this.auth.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}
