import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiClient } from '../../../core/api/api-client';
import { GroupAdminService } from '../group-admin.service';
import {
  Court,
  CourtListResponse,
  DeleteCourtResponse,
  RegenerateControlPanelLinkResponse,
  RegenerateScoreboardLinkResponse,
} from './court-management.models';

/** Centralized API layer for the court-management feature (T011). Reuses
 * GroupAdminService's stored admin_token — court endpoints are guarded by
 * the same `require_admin` dependency as the group endpoints. */
@Injectable({ providedIn: 'root' })
export class CourtManagementService {
  private readonly api = inject(ApiClient);
  private readonly groupAdmin = inject(GroupAdminService);

  createCourt(groupId: string, name: string): Observable<Court> {
    return this.api.post<Court>(
      `/groups/${groupId}/courts`,
      { name },
      this.authHeader(groupId),
    );
  }

  listCourts(groupId: string): Observable<CourtListResponse> {
    return this.api.get<CourtListResponse>(
      `/groups/${groupId}/courts`,
      this.authHeader(groupId),
    );
  }

  renameCourt(groupId: string, courtId: string, name: string): Observable<Court> {
    return this.api.patch<Court>(
      `/courts/${courtId}`,
      { name },
      this.authHeader(groupId),
    );
  }

  deleteCourt(groupId: string, courtId: string): Observable<DeleteCourtResponse> {
    return this.api.delete<DeleteCourtResponse>(
      `/courts/${courtId}`,
      this.authHeader(groupId),
    );
  }

  regenerateScoreboardLink(
    groupId: string,
    courtId: string,
    expectedVersion: number,
  ): Observable<RegenerateScoreboardLinkResponse> {
    return this.api.post<RegenerateScoreboardLinkResponse>(
      `/courts/${courtId}/regenerate-scoreboard-link`,
      { expected_version: expectedVersion },
      this.authHeader(groupId),
    );
  }

  regenerateControlPanelLink(
    groupId: string,
    courtId: string,
    expectedVersion: number,
  ): Observable<RegenerateControlPanelLinkResponse> {
    return this.api.post<RegenerateControlPanelLinkResponse>(
      `/courts/${courtId}/regenerate-control-panel-link`,
      { expected_version: expectedVersion },
      this.authHeader(groupId),
    );
  }

  private authHeader(groupId: string): Record<string, string> {
    const token = this.groupAdmin.getAdminToken(groupId);
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}
