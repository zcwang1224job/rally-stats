import { MatchRecordDetailResponse } from '../api/group-member-view.models';
import { Team } from '../../features/group-admin/schedule-management/schedule.models';
import { formatPercent } from '../match-record-detail/ratio-format';
import { Highlight } from './share-card.models';

const MAX_HIGHLIGHTS = 3;

/** Thresholds that scale with the match's points to win (spec FR-012,
 * clarified 2026-09-21): at 21 points they are 3 / 5 / 10. */
const COMEBACK_RATIO = 0.15;
const RUN_RATIO = 0.25;
const MARGIN_RATIO = 0.5;
/** Fixed thresholds: ratios and counts that don't depend on match length. */
const ENDING_COVERAGE = 0.8;
const WINNER_SHARE = 0.5;
const LEAD_CHANGES = 3;

/** `max(3, floor(T × ratio))` — the floor of 3 keeps a short game from
 * turning "2 in a row" into a highlight of nearly every match. */
export function highlightThreshold(targetScore: number, ratio: number): number {
  return Math.max(3, Math.floor(targetScore * ratio));
}

/** 040-match-share-card research.md Decision 7: up to three highlights for
 * the protagonist — the winner on a neutral card, the viewer's own team on
 * "my" card. Every number is read straight off the detail's existing stats
 * (FR-010); candidates are tried in a fixed priority order, so the same
 * match always gives the same highlights (FR-015). */
export function pickHighlights(detail: MatchRecordDetailResponse, protagonist: Team): Highlight[] {
  // FR-011: a partial record gets no highlights at all, never ones worked
  // out from half a match.
  if (detail.record_completeness !== 'complete') {
    return [];
  }
  const target = detail.target_score;
  const won = detail.winner_team === protagonist;
  const scoreFor = protagonist === 'A' ? detail.score_a : detail.score_b;
  const scoreAgainst = protagonist === 'A' ? detail.score_b : detail.score_a;
  const clutch = detail.clutch_stats;
  const momentum = detail.momentum_stats;
  const ending = detail.ending_stats;
  const picked: Highlight[] = [];

  // 1. Came back to win. `comeback` exists only when the winner trailed.
  const comeback = clutch?.comeback;
  if (
    comeback &&
    comeback.winner === protagonist &&
    comeback.max_deficit >= highlightThreshold(target, COMEBACK_RATIO)
  ) {
    picked.push({ kind: 'comeback', deficit: comeback.max_deficit });
  }

  // 2. Saved the opponent's match points — worth saying even in a loss.
  const saved = clutch?.match_points.find((m) => m.team === protagonist)?.saved ?? 0;
  if (saved >= 1) {
    picked.push({ kind: 'matchPointsSaved', count: saved });
  }

  // 3. Won after reaching deuce.
  if (clutch?.deuce && won) {
    picked.push({ kind: 'deuceWin', scoreFor, scoreAgainst });
  }

  // 4. Longest run of points in a row.
  const run = momentum?.longest_runs.find((r) => r.team === protagonist)?.length ?? 0;
  if (run >= highlightThreshold(target, RUN_RATIO)) {
    picked.push({ kind: 'run', length: run });
  }

  // 5. Share of the protagonist's points that were winners — only when
  // enough points had an ending recorded to say so (FR-014).
  const winners = ending?.teams.find((t) => t.team === protagonist)?.winners ?? 0;
  if (
    ending &&
    ending.total_points > 0 &&
    ending.recorded_points / ending.total_points >= ENDING_COVERAGE &&
    scoreFor > 0 &&
    winners / scoreFor >= WINNER_SHARE
  ) {
    picked.push({ kind: 'winnerRate', percent: formatPercent(winners / scoreFor) });
  }

  // 6. A back-and-forth match — about the match, not one side.
  const leadChanges = momentum?.lead_changes.length ?? 0;
  if (leadChanges >= LEAD_CHANGES) {
    picked.push({ kind: 'leadChanges', count: leadChanges });
  }

  // 7. Won by a wide margin.
  const margin = scoreFor - scoreAgainst;
  if (won && margin >= highlightThreshold(target, MARGIN_RATIO)) {
    picked.push({ kind: 'bigMargin', margin });
  }

  return picked.slice(0, MAX_HIGHLIGHTS);
}
