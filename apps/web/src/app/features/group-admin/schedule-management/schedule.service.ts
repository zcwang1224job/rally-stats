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

  /** 018-plan-then-start: 「結束這一輪」——強制把本輪還沒打完的比賽視為
   * 已捨棄，但不產生新的一輪（round_number 不變）。結束後 round_phase 會
   * 變成 'awaiting_plan'，管理員接著呼叫 `planRound`。manual 模式不適用。 */
  endRound(groupId: string): Observable<ScheduleResponse> {
    return this.api.post<ScheduleResponse>(
      `/groups/${groupId}/schedule/end-round`,
      {},
      this.authHeader(groupId),
    );
  }

  /** 018-plan-then-start: 「規劃賽程安排」——產生本輪配對但不派上場地，讓
   * 管理員能在按下「比賽開始」（`startRound`）前用 `getRoundMatches` 檢視、
   * 用 `swapPlannedMatchPlayers`/`reorderPlannedMatches` 調整。manual 模式
   * 不適用，仍走 `nextRound`。 */
  planRound(groupId: string, temporaryPairings?: TemporaryPairing[]): Observable<ScheduleResponse> {
    const body = temporaryPairings?.length
      ? {
          temporary_pairings: temporaryPairings.map((pairing) => ({
            player_a_id: pairing.player_a.roster_entry_id,
            player_b_id: pairing.player_b.roster_entry_id,
          })),
        }
      : {};
    return this.api.post<ScheduleResponse>(
      `/groups/${groupId}/schedule/plan`,
      body,
      this.authHeader(groupId),
    );
  }

  /** 018-plan-then-start: 確認已規劃好的賽程，把比賽派上場地開打。 */
  startRound(groupId: string): Observable<ScheduleResponse> {
    return this.api.post<ScheduleResponse>(
      `/groups/${groupId}/schedule/start`,
      {},
      this.authHeader(groupId),
    );
  }

  /** 018-plan-then-start: 交換兩位選手在任兩場「尚未結束」（queued 或
   * in_progress）比賽中的場次——包含賽程已經開打的情況（例如有人受傷需要
   * 替補），不限於「已規劃、尚未開打」階段。 */
  swapPlannedMatchPlayers(
    groupId: string,
    matchId1: string,
    rosterEntryId1: string,
    matchId2: string,
    rosterEntryId2: string,
  ): Observable<RoundMatchesResponse> {
    return this.api.post<RoundMatchesResponse>(
      `/groups/${groupId}/schedule/matches/swap`,
      {
        match_id_1: matchId1,
        roster_entry_id_1: rosterEntryId1,
        match_id_2: matchId2,
        roster_entry_id_2: rosterEntryId2,
      },
      this.authHeader(groupId),
    );
  }

  /** 018-plan-then-start: 直接把某場「尚未結束」比賽中的某位選手換成
   * 指定的另一位成員（不透過「跟另一場互換」）——例如找一位候補上場。 */
  changeMatchPlayer(
    groupId: string,
    matchId: string,
    oldRosterEntryId: string,
    newRosterEntryId: string,
  ): Observable<RoundMatchesResponse> {
    return this.api.post<RoundMatchesResponse>(
      `/groups/${groupId}/schedule/matches/change-player`,
      {
        match_id: matchId,
        old_roster_entry_id: oldRosterEntryId,
        new_roster_entry_id: newRosterEntryId,
      },
      this.authHeader(groupId),
    );
  }

  /** 018-plan-then-start: 拖曳調整「已規劃、尚未開打」賽程的叫號順序——
   * `matchIds` 必須是本輪現有比賽 id 的完整排列（只是重排，不是增減）。 */
  reorderPlannedMatches(groupId: string, matchIds: string[]): Observable<RoundMatchesResponse> {
    return this.api.post<RoundMatchesResponse>(
      `/groups/${groupId}/schedule/matches/reorder`,
      { match_ids: matchIds },
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
