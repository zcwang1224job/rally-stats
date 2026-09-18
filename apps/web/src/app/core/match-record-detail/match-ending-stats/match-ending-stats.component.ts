import { Component, computed, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { Team } from '../../../features/group-admin/schedule-management/schedule.models';
import { EndingStats, PlayerEndingStat } from '../../api/group-member-view.models';

/** 035-point-ending-type: how the match's points were won — winners vs.
 * errors — per team and per player. **Purely presentational**, same
 * contract as `MatchClutchStatsComponent`: every number is computed once,
 * on the backend (`match_stats.ending_stats`), and each player's two
 * triples already add up to their `player_stats` totals (FR-015).
 *
 * "Winner" and "error" are told apart by an icon + text, never by colour
 * alone (FR-014). `endingStats` null → one notice, no table (FR-017): either
 * the record is incomplete or not one point of the match recorded an
 * ending (every pre-035 match). */
@Component({
  selector: 'app-match-ending-stats',
  imports: [TranslatePipe],
  templateUrl: './match-ending-stats.component.html',
  styleUrl: './match-ending-stats.component.scss',
})
export class MatchEndingStatsComponent {
  readonly endingStats = input.required<EndingStats | null>();

  /** Per-player rows in the order the response gives (team_a + team_b),
   * each with the totals the six columns add up to — shown so a reader can
   * check the split against the familiar "scored / fault" numbers. */
  readonly playerRows = computed(() =>
    (this.endingStats()?.players ?? []).map((player: PlayerEndingStat) => ({
      ...player,
      scored_total: player.winners + player.opponent_errors + player.scored_unrecorded,
      lost_total: player.beaten_by_winners + player.own_errors + player.lost_unrecorded,
    })),
  );

  teamLabelKey(team: Team): string {
    return team === 'A' ? 'matchRecordDetail.derived.teamA' : 'matchRecordDetail.derived.teamB';
  }
}
