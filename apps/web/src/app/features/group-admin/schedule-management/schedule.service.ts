import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiClient } from '../../../core/api/api-client';
import { JoinGroupResponse } from '../../../core/api/group-join.models';
import { GroupAdminService } from '../group-admin.service';
import {
  KickMemberResponse,
  MatchDetailResponse,
  PartnershipsResponse,
  RegenerateGuestLinkResponse,
  RoundMatchesResponse,
  ScheduleResponse,
  ScoreMutationResult,
  Team,
  TemporaryPairing,
  TemporaryPairingsResponse,
} from './schedule.models';

/** Centralized API layer for the schedule-management feature (US1 T026/T027
 * onward). Reuses GroupAdminService's stored admin_token, same as
 * CourtManagementService — every endpoint here is `require_admin`-gated. */
@Injectable({ providedIn: 'root' })
export class ScheduleService {
  private readonly api = inject(ApiClient);
  private readonly groupAdmin = inject(GroupAdminService);

  getSchedule(groupId: string): Observable<ScheduleResponse> {
    return this.api.get<ScheduleResponse>(`/groups/${groupId}/schedule`, this.authHeader(groupId));
  }

  getRoundMatches(groupId: string): Observable<RoundMatchesResponse> {
    return this.api.get<RoundMatchesResponse>(
      `/groups/${groupId}/schedule/matches`,
      this.authHeader(groupId),
    );
  }

  nextRound(
    groupId: string,
    temporaryPairings?: TemporaryPairing[],
  ): Observable<ScheduleResponse> {
    const body = temporaryPairings?.length
      ? {
          temporary_pairings: temporaryPairings.map((pairing) => ({
            player_a_id: pairing.player_a.roster_entry_id,
            player_b_id: pairing.player_b.roster_entry_id,
          })),
        }
      : {};
    return this.api.post<ScheduleResponse>(
      `/groups/${groupId}/next-round`,
      body,
      this.authHeader(groupId),
    );
  }

  previewRandomPairing(groupId: string): Observable<TemporaryPairingsResponse> {
    return this.api.post<TemporaryPairingsResponse>(
      `/groups/${groupId}/partnerships/random-preview`,
      {},
      this.authHeader(groupId),
    );
  }

  setAutoNextRound(groupId: string, enabled: boolean): Observable<{ auto_next_round: boolean }> {
    return this.api.patch<{ auto_next_round: boolean }>(
      `/groups/${groupId}/auto-next-round`,
      { enabled },
      this.authHeader(groupId),
    );
  }

  manualAssign(
    groupId: string,
    courtId: string,
    participantIds: string[],
    teams: Record<string, Team>,
  ): Observable<MatchDetailResponse> {
    return this.api.post<MatchDetailResponse>(
      `/courts/${courtId}/manual-assign`,
      { participant_ids: participantIds, teams },
      this.authHeader(groupId),
    );
  }

  getPartnerships(groupId: string): Observable<PartnershipsResponse> {
    return this.api.get<PartnershipsResponse>(
      `/groups/${groupId}/partnerships`,
      this.authHeader(groupId),
    );
  }

  reassignPartnership(
    groupId: string,
    playerAId: string,
    playerBId: string,
  ): Observable<PartnershipsResponse> {
    return this.api.patch<PartnershipsResponse>(
      `/groups/${groupId}/partnerships`,
      { player_a_id: playerAId, player_b_id: playerBId },
      this.authHeader(groupId),
    );
  }

  dissolvePartnership(groupId: string, rosterEntryId: string): Observable<PartnershipsResponse> {
    return this.api.delete<PartnershipsResponse>(
      `/groups/${groupId}/partnerships/${rosterEntryId}`,
      this.authHeader(groupId),
    );
  }

  scoreMatch(
    groupId: string,
    courtId: string,
    matchId: string,
    side: Team,
    delta: 1 | -1,
  ): Observable<ScoreMutationResult> {
    return this.api.post<ScoreMutationResult>(
      `/groups/${groupId}/courts/${courtId}/matches/${matchId}/score`,
      { side, delta },
      this.authHeader(groupId),
    );
  }

  endMatch(groupId: string, courtId: string, matchId: string): Observable<ScoreMutationResult> {
    return this.api.post<ScoreMutationResult>(
      `/groups/${groupId}/courts/${courtId}/matches/${matchId}/end`,
      {},
      this.authHeader(groupId),
    );
  }

  kickMember(groupId: string, rosterEntryId: string): Observable<KickMemberResponse> {
    return this.api.delete<KickMemberResponse>(
      `/groups/${groupId}/members/${rosterEntryId}`,
      this.authHeader(groupId),
    );
  }

  addGuest(groupId: string, nickname: string): Observable<JoinGroupResponse> {
    return this.api.post<JoinGroupResponse>(
      `/groups/${groupId}/members`,
      { nickname },
      this.authHeader(groupId),
    );
  }

  regenerateGuestLink(
    groupId: string,
    rosterEntryId: string,
  ): Observable<RegenerateGuestLinkResponse> {
    return this.api.post<RegenerateGuestLinkResponse>(
      `/groups/${groupId}/members/${rosterEntryId}/regenerate-guest-link`,
      {},
      this.authHeader(groupId),
    );
  }

  private authHeader(groupId: string): Record<string, string> {
    const token = this.groupAdmin.getAdminToken(groupId);
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}
