import { MatchRecordDetailResponse, ScoreEventSummary } from '../api/group-member-view.models';

/** One point of the score trend, in percent of the plot area: x from the
 * left edge, yA/yB from the TOP edge (0 = top = the higher final score). */
export interface ScoreTrendPoint {
  x: number;
  yA: number;
  yB: number;
  elapsedSeconds: number;
  scoreA: number;
  scoreB: number;
}

/** 016-match-score-timeline research.md #3: the x-axis is elapsed seconds
 * since match start. For a `"complete"` record, a synthetic (0, 0:0) origin
 * point is prepended — the match really did start there. For `"partial"`,
 * that origin is unknown and MUST NOT be fabricated (FR-006a), so the line
 * starts at the first recorded event's already-elevated score.
 *
 * Shared by the match detail chart and the 040 share card (research.md
 * Decision 4), so the two can never draw different shapes. */
export function buildScoreTrendPoints(detail: MatchRecordDetailResponse): ScoreTrendPoint[] | null {
  if (detail.events.length === 0) {
    return null;
  }
  const events: ScoreEventSummary[] =
    detail.record_completeness === 'complete'
      ? [
          { side: 'A', delta: 1, score_a: 0, score_b: 0, elapsed_seconds: 0, detail: null },
          ...detail.events,
        ]
      : detail.events;
  const maxElapsed = Math.max(events[events.length - 1].elapsed_seconds, 1);
  const maxScore = Math.max(detail.score_a, detail.score_b, 1);
  return events.map((event) => ({
    x: (event.elapsed_seconds / maxElapsed) * 100,
    yA: 100 - (event.score_a / maxScore) * 100,
    yB: 100 - (event.score_b / maxScore) * 100,
    elapsedSeconds: event.elapsed_seconds,
    scoreA: event.score_a,
    scoreB: event.score_b,
  }));
}
