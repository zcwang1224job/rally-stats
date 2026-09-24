import { Component, computed, input, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { Team } from '../../../features/group-admin/schedule-management/schedule.models';
import {
  MatchRecordDetailResponse,
  PlayerLandingDistribution,
} from '../../api/group-member-view.models';
import { CourtDiagramComponent, CourtMarker } from '../../court-diagram/court-diagram.component';
import { NicknameComponent } from '../../nickname/nickname.component';
import { MatchClutchStatsComponent } from '../match-clutch-stats/match-clutch-stats.component';
import { MatchEndingStatsComponent } from '../match-ending-stats/match-ending-stats.component';
import { percentOrDash } from '../ratio-format';

/** 033-match-record-derived-stats: the derived blocks of the match detail
 * dialog — serve/receive win rate, momentum, per-point tempo, and per-player
 * landing distribution — plus 034's clutch-point block and 035's
 * winners-vs-errors block, which live in their own components
 * (`MatchClutchStatsComponent`, `MatchEndingStatsComponent`) and are only
 * hosted here.
 * **Purely presentational**: every number
 * arrives already computed on `detail` (the rules — which points still
 * stand after a correction, who was serving — exist once, on the backend);
 * the only arithmetic here is turning won/total into a percentage.
 *
 * Each block is a native `<details>`, collapsed by default so the dialog's
 * existing content isn't pushed out of reach on a phone, and each shows its
 * own "no data" notice when its field is null/empty — one block lacking
 * data never blanks the others. */
@Component({
  selector: 'app-match-derived-stats',
  imports: [
    TranslatePipe,
    NicknameComponent,
    CourtDiagramComponent,
    MatchClutchStatsComponent,
    MatchEndingStatsComponent,
  ],
  templateUrl: './match-derived-stats.component.html',
  styleUrl: './match-derived-stats.component.scss',
})
export class MatchDerivedStatsComponent {
  readonly detail = input.required<MatchRecordDetailResponse>();

  /** Same derivation the dialog uses — participant count, no extra field. */
  readonly isSinglesMatch = computed(() => {
    const d = this.detail();
    return d.team_a.length + d.team_b.length <= 2;
  });

  readonly showScored = signal(true);
  readonly showLost = signal(true);
  private readonly pickedPlayerId = signal<string | null>(null);

  /** The picked player if they're part of THIS match's distribution,
   * otherwise the first player with anything plotted — so a pick made on one
   * match never leaks into the next one the same dialog instance shows. */
  readonly players = computed<PlayerLandingDistribution[]>(
    // `?? []`: a response from a backend that predates this field (frontend
    // deployed first) must read as "no data", not crash the whole dialog.
    () => this.detail().landing_distribution ?? [],
  );

  readonly selectedPlayer = computed<PlayerLandingDistribution | null>(() => {
    const players = this.players();
    return (
      players.find((p) => p.roster_entry_id === this.pickedPlayerId()) ??
      players.find((p) => p.scored.length + p.lost.length > 0) ??
      players[0] ??
      null
    );
  });

  readonly markers = computed<CourtMarker[]>(() => {
    const player = this.selectedPlayer();
    if (!player) {
      return [];
    }
    return [
      ...(this.showScored() ? player.scored.map((p) => ({ ...p, kind: 'scored' as const })) : []),
      ...(this.showLost() ? player.lost.map((p) => ({ ...p, kind: 'lost' as const })) : []),
    ];
  });

  selectPlayer(rosterEntryId: string): void {
    this.pickedPlayerId.set(rosterEntryId);
  }

  teamLabelKey(team: Team): string {
    return team === 'A' ? 'matchRecordDetail.derived.teamA' : 'matchRecordDetail.derived.teamB';
  }

  readonly percent = percentOrDash;

  /** Key + params for the template's translate pipe — no copy is assembled
   * here. Under a minute keeps the one decimal the average carries; from a
   * minute up that precision is noise, so whole seconds. */
  duration(seconds: number): { key: string; params: Record<string, number> } {
    if (seconds < 60) {
      return { key: 'matchRecordDetail.derived.tempo.seconds', params: { seconds } };
    }
    const whole = Math.round(seconds);
    return {
      key: 'matchRecordDetail.derived.tempo.minutesSeconds',
      params: { minutes: Math.floor(whole / 60), seconds: whole % 60 },
    };
  }
}
