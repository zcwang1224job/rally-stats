import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiClient } from './api-client';
import {
  AllCourtsLiveState,
  CourtStateResponse,
  ScoreMutationResult,
  Team,
} from './court-live-state.models';

/** +1/-1、提前結束、即時狀態拉取（初始載入 + 斷線重連強制覆蓋）——
 * 單一場地控制板/計分板、全部場地控制板共用，per contracts/scoring-api.md. */
@Injectable({ providedIn: 'root' })
export class CourtControlService {
  private readonly api = inject(ApiClient);

  getState(token: string): Observable<CourtStateResponse> {
    return this.api.get<CourtStateResponse>(`/courts/by-token/${token}/state`);
  }

  score(
    token: string,
    matchId: string,
    side: Team,
    delta: 1 | -1,
  ): Observable<ScoreMutationResult> {
    return this.api.post<ScoreMutationResult>(
      `/courts/by-token/${token}/matches/${matchId}/score`,
      { side, delta },
    );
  }

  endMatch(token: string, matchId: string): Observable<ScoreMutationResult> {
    return this.api.post<ScoreMutationResult>(`/courts/by-token/${token}/matches/${matchId}/end`);
  }

  getAllCourtsState(token: string): Observable<AllCourtsLiveState> {
    return this.api.get<AllCourtsLiveState>(`/groups/by-all-courts-token/${token}/state`);
  }

  scoreAllCourts(
    token: string,
    courtId: string,
    matchId: string,
    side: Team,
    delta: 1 | -1,
  ): Observable<ScoreMutationResult> {
    return this.api.post<ScoreMutationResult>(
      `/groups/by-all-courts-token/${token}/courts/${courtId}/matches/${matchId}/score`,
      { side, delta },
    );
  }

  endMatchAllCourts(token: string, courtId: string, matchId: string): Observable<ScoreMutationResult> {
    return this.api.post<ScoreMutationResult>(
      `/groups/by-all-courts-token/${token}/courts/${courtId}/matches/${matchId}/end`,
    );
  }
}
