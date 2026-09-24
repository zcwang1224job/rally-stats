import { Observable } from 'rxjs';

import { CourtControlService } from '../../core/api/court-control.service';
import { ParticipantSummary, Team } from '../../core/api/court-live-state.models';
import { EndMode, SportSummary } from '../../core/api/sport.models';
import { ScheduleService } from '../../features/group-admin/schedule-management/schedule.service';

/**
 * 043: what a sport type's score pad needs from a match in progress. Both
 * the public live state (`MatchLiveDetail`) and the admin schedule
 * (`MatchSummary`) have these fields, so one pad serves every face.
 */
export interface LiveMatch {
  readonly match_id: string;
  readonly participants: readonly ParticipantSummary[];
  readonly score_a: number;
  readonly score_b: number;
  readonly target_score?: number;
  readonly end_mode?: EndMode;
  readonly allow_draw?: boolean;
  readonly score_steps?: readonly number[];
  readonly sport?: SportSummary;
  readonly sport_state?: unknown;
}

/** The parts of a scoring response every face returns. */
export interface ScoringResult {
  readonly applied: boolean;
  readonly match_id: string;
  readonly status: string;
  readonly score_a: number;
  readonly score_b: number;
  readonly winner_team: Team | 'D' | null;
  readonly sport_state?: unknown;
}

/**
 * The scorer actions of one court, whichever authorization face the page
 * is on (court link, all-courts link, admin) — constitution IV: scoring is
 * never admin-only, so every face gets the same set.
 */
export interface ScoringActions {
  score(matchId: string, side: Team, delta: number): Observable<ScoringResult>;
  applyEvent(matchId: string, kind: string, payload: Record<string, unknown>): Observable<ScoringResult>;
  undo(matchId: string): Observable<ScoringResult>;
  /** "End and record the result" (manual-end matches). */
  finish(matchId: string): Observable<ScoringResult>;
  /** "Abandon the match": no result recorded. */
  abandon(matchId: string): Observable<ScoringResult>;
}

export function courtLinkActions(service: CourtControlService, token: string): ScoringActions {
  return {
    score: (matchId, side, delta) => service.score(token, matchId, side, delta),
    applyEvent: (matchId, kind, payload) => service.applyEvent(token, matchId, kind, payload),
    undo: (matchId) => service.undoLastEvent(token, matchId),
    finish: (matchId) => service.finishMatch(token, matchId),
    abandon: (matchId) => service.endMatch(token, matchId),
  };
}

export function allCourtsActions(
  service: CourtControlService,
  token: string,
  courtId: string,
): ScoringActions {
  return {
    score: (matchId, side, delta) => service.scoreAllCourts(token, courtId, matchId, side, delta),
    applyEvent: (matchId, kind, payload) =>
      service.applyEventAllCourts(token, courtId, matchId, kind, payload),
    undo: (matchId) => service.undoLastEventAllCourts(token, courtId, matchId),
    finish: (matchId) => service.finishMatchAllCourts(token, courtId, matchId),
    abandon: (matchId) => service.endMatchAllCourts(token, courtId, matchId),
  };
}

export function adminActions(
  service: ScheduleService,
  groupId: string,
  courtId: string,
): ScoringActions {
  return {
    score: (matchId, side, delta) => service.scoreMatch(groupId, courtId, matchId, side, delta),
    applyEvent: (matchId, kind, payload) =>
      service.applyEvent(groupId, courtId, matchId, kind, payload),
    undo: (matchId) => service.undoLastEvent(groupId, courtId, matchId),
    finish: (matchId) => service.finishMatch(groupId, courtId, matchId),
    abandon: (matchId) => service.endMatch(groupId, courtId, matchId),
  };
}
