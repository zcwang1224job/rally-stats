import { formatDate } from '@angular/common';
import { MatchRecordDetailResponse } from '../api/group-member-view.models';
import { Team } from '../../features/group-admin/schedule-management/schedule.models';
import { buildScoreTrendPoints } from '../match-record-detail/score-trend';
import { CardBadge, CardTeam, ShareCardContext, ShareCardModel } from './share-card.models';
import { pickHighlights } from './share-card-highlights';

/** 040-match-share-card: turns one match detail plus the caller's context
 * into everything the card shows. Pure — no DOM, no translation; wording is
 * left as language keys for the renderer (research.md Decision 2). */
export function buildShareCardModel(
  detail: MatchRecordDetailResponse,
  context: ShareCardContext,
): ShareCardModel {
  const perspective = context.perspective;
  // 043: a draw has no winner; the card then takes team A's side.
  const winner: Team = detail.winner_team === 'B' ? 'B' : 'A';
  const protagonist: Team = perspective.kind === 'mine' ? perspective.myTeam : winner;
  const other: Team = protagonist === 'A' ? 'B' : 'A';
  const teams: [CardTeam, CardTeam] = [
    cardTeam(detail, protagonist, context),
    cardTeam(detail, other, context),
  ];
  const complete = detail.record_completeness === 'complete';
  const winnerNames = (detail.winner_team === 'A' ? detail.team_a : detail.team_b)
    .map((p) => p.nickname)
    .join('、');

  return {
    groupName: context.groupName,
    startedAt: detail.started_at,
    roundNumber: detail.round_number,
    perspective: perspective.kind,
    teams,
    // FR-007/FR-009/FR-011: a partial or missing point record gets none of
    // the point-derived parts, rather than parts computed from half a match.
    trend: complete ? buildScoreTrendPoints(detail) : null,
    highlights: complete ? pickHighlights(detail, protagonist) : [],
    averagePointSeconds: complete ? (detail.tempo_stats?.average_seconds ?? null) : null,
    durationSeconds: durationSeconds(detail.started_at, detail.ended_at),
    fileName: fileName(detail.started_at, teams),
    altText: {
      key: 'matchShareCard.altText',
      params: {
        first: teams[0].nicknames.join('、'),
        firstScore: teams[0].score,
        second: teams[1].nicknames.join('、'),
        secondScore: teams[1].score,
        winner: winnerNames,
      },
    },
  };
}

function cardTeam(
  detail: MatchRecordDetailResponse,
  team: Team,
  context: ShareCardContext,
): CardTeam {
  const isWinner = detail.winner_team === team;
  return {
    team,
    nicknames: (team === 'A' ? detail.team_a : detail.team_b).map((p) => p.nickname),
    score: team === 'A' ? detail.score_a : detail.score_b,
    isWinner,
    badge: badgeFor(team, isWinner, context),
  };
}

/** FR-016/FR-017: only the viewer's own card says Victory/Defeat; a neutral
 * card just marks the winner. */
function badgeFor(team: Team, isWinner: boolean, context: ShareCardContext): CardBadge | null {
  const perspective = context.perspective;
  if (perspective.kind === 'mine') {
    if (team !== perspective.myTeam) {
      return null;
    }
    return isWinner ? 'victory' : 'defeat';
  }
  return isWinner ? 'win' : null;
}

function durationSeconds(startedAt: string | null, endedAt: string | null): number | null {
  if (!startedAt || !endedAt) {
    return null;
  }
  const seconds = Math.round((Date.parse(endedAt) - Date.parse(startedAt)) / 1000);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

/** The date is the device-local one, like every other match time in the
 * app (research.md Decision 8). */
function fileName(startedAt: string | null, teams: [CardTeam, CardTeam]): string {
  const scores = `${teams[0].score}-${teams[1].score}`;
  return startedAt
    ? `rally-stats-${formatDate(startedAt, 'yyyyMMdd', 'en-US')}-${scores}.png`
    : `rally-stats-${scores}.png`;
}
