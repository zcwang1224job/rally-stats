import { formatPercent } from '../match-record-detail/ratio-format';
import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, input, output, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { MatchupRecord } from '../api/group-member-view.models';
import { NicknameComponent } from '../nickname/nickname.component';

export type MatchupSort = 'matches' | 'win_rate' | 'avg_margin';
export type MatchupRole = 'partner' | 'opponent';

interface Highlight {
  labelKey: string;
  record: MatchupRecord;
}

const SORTS: MatchupSort[] = ['matches', 'win_rate', 'avg_margin'];

/** 036 US2: partners, or opponents, of one member — matches, record, win rate
 * and average margin per player. Shared by the member's own page (rows are
 * buttons that narrow the whole page to that player) and a friend's page
 * (`clickable` false: plain rows, FR-037).
 *
 * The three sort orders only re-arrange the rows it was given — presentation,
 * not a statistic. WHO gets highlighted is decided on the backend
 * (`matchups.py`) and arrives as player keys. */
@Component({
  selector: 'app-matchup-records',
  imports: [TranslatePipe, NicknameComponent, NgTemplateOutlet],
  templateUrl: './matchup-records.component.html',
  styleUrl: './matchup-records.component.scss',
})
export class MatchupRecordsComponent {
  readonly role = input.required<MatchupRole>();
  readonly records = input.required<MatchupRecord[]>();
  /** Backend-picked player keys: the most played, and the best (partner) /
   * toughest (opponent). Null when nobody has played enough. */
  readonly mostPlayedKey = input<string | null>(null);
  readonly standoutKey = input<string | null>(null);
  /** Shown instead of the table when there is nothing to list — for partners,
   * "singles has no partner" when the member never played doubles. */
  readonly emptyKey = input<string | null>(null);
  readonly clickable = input(true);

  readonly picked = output<MatchupRecord>();
  /** Starts open; a host page running its sections as an accordion binds it
   * and listens to `openChange` for the reader's own clicks. */
  readonly open = input(true);
  readonly openChange = output<boolean>();

  onToggle(event: Event): void {
    this.openChange.emit((event.target as HTMLDetailsElement).open);
  }

  readonly sorts = SORTS;
  readonly sort = signal<MatchupSort>('matches');

  readonly titleKey = computed(() => `member.matchHistory.matchups.${this.role()}Title`);

  readonly sorted = computed<MatchupRecord[]>(() => {
    const by = this.sort();
    // The incoming order (matches desc, then key) is the tie-break for every
    // sort, so equal rows never swap places between renders.
    return this.records()
      .map((record, index) => ({ record, index }))
      .sort((a, b) => b.record[by] - a.record[by] || a.index - b.index)
      .map(({ record }) => record);
  });

  readonly highlights = computed<Highlight[]>(() => {
    const byKey = new Map(this.records().map((record) => [record.player_key, record]));
    const found: Highlight[] = [];
    const most = this.mostPlayedKey() ? byKey.get(this.mostPlayedKey()!) : undefined;
    const standout = this.standoutKey() ? byKey.get(this.standoutKey()!) : undefined;
    if (most) {
      found.push({ labelKey: `member.matchHistory.matchups.highlights.${this.role()}Most`, record: most });
    }
    if (standout) {
      found.push({
        labelKey: `member.matchHistory.matchups.highlights.${this.role()}Standout`,
        record: standout,
      });
    }
    return found;
  });

  percent(rate: number): string {
    return formatPercent(rate);
  }

  /** "+3.5" / "−6.0": the real minus sign, so the column lines up. */
  margin(value: number): string {
    const rounded = Math.abs(value).toFixed(1);
    if (Number(rounded) === 0) {
      return '±0.0';
    }
    return `${value > 0 ? '+' : '−'}${rounded}`;
  }

  rowId(record: MatchupRecord): string {
    return `matchup-${this.role()}-${record.player_key}`;
  }
}
