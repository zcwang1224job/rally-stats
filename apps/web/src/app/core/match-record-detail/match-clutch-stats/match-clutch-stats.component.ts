import { Component, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { Team } from '../../../features/group-admin/schedule-management/schedule.models';
import { ClutchStats } from '../../api/group-member-view.models';
import { percentOrDash } from '../ratio-format';

/** 034-clutch-points-player-dashboard: how each TEAM did when it mattered —
 * endgame, deuce, match points, win rate by score state, and the comeback
 * line. **Purely presentational**, same contract as its host
 * `MatchDerivedStatsComponent`: which points count as "endgame" or as a
 * match point is decided once, on the backend (`match_stats.clutch_stats`).
 *
 * Three different "nothing to show" cases, deliberately not merged:
 * - `clutchStats` null → the record is incomplete → one notice for the block;
 * - a phase is null → it doesn't apply / never happened → a sentence;
 * - a total is 0 → it applies but never occurred → "0/0 —", never 0%. */
@Component({
  selector: 'app-match-clutch-stats',
  imports: [TranslatePipe],
  templateUrl: './match-clutch-stats.component.html',
  styleUrl: './match-clutch-stats.component.scss',
})
export class MatchClutchStatsComponent {
  readonly clutchStats = input.required<ClutchStats | null>();

  readonly percent = percentOrDash;

  teamLabelKey(team: Team): string {
    return team === 'A' ? 'matchRecordDetail.derived.teamA' : 'matchRecordDetail.derived.teamB';
  }
}
