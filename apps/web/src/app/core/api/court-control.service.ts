import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiClient } from './api-client';
import {
  AllCourtsLiveState,
  CourtStateResponse,
  ScoreMutationResult,
  ShotPlacementAttachResponse,
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

  /** 032-score-then-record: attaches landing/player detail to a `+1` that's
   * already been applied via score() above — pressing "+" bumps the score
   * immediately (match pace never waits on the detail dialog); this is
   * what the picker's confirm() calls afterward, pinned to the exact
   * ScoreEvent that "+" created (`scoreEventId`, from that score() call's
   * own response) rather than "the most recent point", so a rapid string
   * of points can't mismatch which point an answer lands on. */
  recordShotPlacement(
    token: string,
    matchId: string,
    scoreEventId: string,
    rosterEntryId: string | null,
    losingRosterEntryId: string | null,
    landingX: number | null,
    landingY: number | null,
  ): Observable<ShotPlacementAttachResponse> {
    return this.api.post<ShotPlacementAttachResponse>(
      `/courts/by-token/${token}/matches/${matchId}/shot-placement`,
      {
        score_event_id: scoreEventId,
        roster_entry_id: rosterEntryId,
        losing_roster_entry_id: losingRosterEntryId,
        landing_x: landingX,
        landing_y: landingY,
      },
    );
  }

  endMatch(token: string, matchId: string): Observable<ScoreMutationResult> {
    return this.api.post<ScoreMutationResult>(`/courts/by-token/${token}/matches/${matchId}/end`);
  }

  /** 032-cancel-score: the picker's "Cancel Score" action's counterpart to
   * score(token, matchId, side, -1) specifically for the point that just
   * completed the match — a plain -1 can't touch an already-`completed`
   * match at all, since apply_score_delta()'s UPDATE requires
   * status='in_progress'. Callers must only reach for this when the point
   * being cancelled is known to have completed the match (see
   * ScoreMutationResult.status from the original score() call); otherwise
   * use the plain score(..., -1) above. */
  undoMatchCompletion(token: string, matchId: string, side: Team): Observable<ScoreMutationResult> {
    return this.api.post<ScoreMutationResult>(
      `/courts/by-token/${token}/matches/${matchId}/undo-completion`,
      { side },
    );
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

  /** 032-cancel-score: all-courts counterpart to undoMatchCompletion() above. */
  undoMatchCompletionAllCourts(
    token: string,
    courtId: string,
    matchId: string,
    side: Team,
  ): Observable<ScoreMutationResult> {
    return this.api.post<ScoreMutationResult>(
      `/groups/by-all-courts-token/${token}/courts/${courtId}/matches/${matchId}/undo-completion`,
      { side },
    );
  }

  /** 032-score-then-record: detailed-mode counterpart to
   * scoreAllCourts() above — see recordShotPlacement()'s doc comment. */
  recordShotPlacementAllCourts(
    token: string,
    courtId: string,
    matchId: string,
    scoreEventId: string,
    rosterEntryId: string | null,
    losingRosterEntryId: string | null,
    landingX: number | null,
    landingY: number | null,
  ): Observable<ShotPlacementAttachResponse> {
    return this.api.post<ShotPlacementAttachResponse>(
      `/groups/by-all-courts-token/${token}/courts/${courtId}/matches/${matchId}/shot-placement`,
      {
        score_event_id: scoreEventId,
        roster_entry_id: rosterEntryId,
        losing_roster_entry_id: losingRosterEntryId,
        landing_x: landingX,
        landing_y: landingY,
      },
    );
  }
}
