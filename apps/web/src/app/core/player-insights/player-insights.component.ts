import { booleanAttribute, Component, computed, inject, input, output } from '@angular/core';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import {
  DashboardInsight,
  DashboardInsights,
  DashboardMetricKey,
  InsightList,
} from '../api/player-dashboard.models';
import {
  byKind,
  insightEvidence,
  insightSentenceKey,
  percent,
  points,
} from './insight-format';

interface InsightSection {
  list: InsightList;
  titleKey: string;
  emptyKey: string;
  items: DashboardInsight[];
}

// Shape carries the meaning, colour only reinforces it (Constitution VII,
// FR-006) — the same marks the metric cards use for a verdict.
const ICON: Record<'strength' | 'weakness' | 'improved' | 'declined' | 'matchup', string> = {
  strength: '▲',
  weakness: '▼',
  improved: '▲',
  declined: '▼',
  matchup: '◆',
};

/** 036 US1: a player's strengths, things to work on, recent changes and
 * notable partners/opponents, as sentences. **Purely presentational** — which
 * insights exist, their order and their strength are decided on the backend
 * (`member/insights.py`); this component never compares two numbers.
 *
 * Shared by the member's own match-history page and a friend's records page
 * (FR-037). */
@Component({
  selector: 'app-player-insights',
  imports: [TranslatePipe],
  templateUrl: './player-insights.component.html',
  styleUrl: './player-insights.component.scss',
})
export class PlayerInsightsComponent {
  private readonly translate = inject(TranslateService);

  readonly insights = input.required<DashboardInsights | null>();
  readonly loading = input(false);
  /** The group benchmark is still loading; its insights will replace these. */
  readonly pendingBenchmark = input(false);
  /** A benchmark group is chosen, but page filters are active (FR-034). */
  readonly benchmarkOmittedByFilters = input(false);
  /** Inside a host page's own collapsible panel, whose summary already
   * carries the title: no card frame and no heading of its own. */
  readonly bare = input(false, { transform: booleanAttribute });

  readonly metricPicked = output<DashboardMetricKey>();
  /** `role` says which table the sentence is about — one player can be in
   * both. */
  readonly playerPicked = output<{ key: string; role: 'partner' | 'opponent' }>();

  readonly sections = computed<InsightSection[]>(() => {
    const found = this.insights();
    if (!found || found.status !== 'ok') {
      return [];
    }
    const all: InsightSection[] = [
      this.section('strength', found.strengths),
      this.section('weakness', found.weaknesses),
      this.section('recent', found.recent),
      this.section('matchup', found.matchups),
    ];
    // The matchup list only exists once partner/opponent records do; an
    // empty one is not worth a heading of its own.
    return all.filter((section) => section.list !== 'matchup' || section.items.length > 0);
  });

  private section(list: InsightList, items: DashboardInsight[]): InsightSection {
    return {
      list,
      items,
      titleKey: `playerInsights.list.${list}`,
      emptyKey: `playerInsights.listEmpty.${list}`,
    };
  }

  sentenceKey(insight: DashboardInsight): string {
    return insightSentenceKey(insight);
  }

  /** Everything a sentence may interpolate. Names (metric labels, error
   * kinds) are looked up here so a sentence reads in one language. */
  sentenceParams(insight: DashboardInsight): Record<string, string | number> {
    const p = insight.params;
    const metric = insight.metric_key
      ? this.translate.instant(`playerDashboard.metric.${insight.metric_key}.label`)
      : '';
    const dominant = p['dominant_error']
      ? this.translate.instant(`playerDashboard.errorBreakdown.kind.${p['dominant_error']}`)
      : '';
    return {
      metric,
      value: percent(p['value']),
      baseline: percent(p['baseline']),
      diff: points(p['diff']),
      dominant,
      dominantShare: percent(p['dominant_share']),
      allValue: byKind(insight, p['all_value']),
      recentValue: byKind(insight, p['recent_value']),
      nickname: insight.player?.nickname ?? '',
      winRate: percent(p['win_rate']),
      group: this.insights()?.benchmark_group_name ?? '',
      mine: byKind(insight, p['mine']),
      groupAverage: byKind(insight, p['group_average']),
      rank: Number(p['rank'] ?? 0),
      pool: Number(p['pool_size'] ?? 0),
    };
  }

  evidenceKey(insight: DashboardInsight): string {
    return `playerInsights.evidence.${insightEvidence(insight)}`;
  }

  evidenceParams(insight: DashboardInsight): Record<string, number> {
    const p = insight.params;
    const n = (key: string): number => Number(p[key] ?? 0);
    return {
      numerator: n('numerator'),
      denominator: n('denominator'),
      matches: n('matches_used') || n('recent_matches_used') || n('matches'),
      wins: n('wins'),
      losses: n('losses'),
      rank: n('rank'),
      pool: n('pool_size'),
    };
  }

  icon(insight: DashboardInsight): string {
    if (insight.list === 'recent') {
      return insight.params['direction'] === 'declined' ? ICON.declined : ICON.improved;
    }
    return ICON[insight.list];
  }

  /** The word next to the icon, so neither colour nor shape is the only cue. */
  toneKey(insight: DashboardInsight): string {
    if (insight.list === 'recent') {
      return `playerDashboard.verdict.${
        insight.params['direction'] === 'declined' ? 'declined' : 'improved'
      }`;
    }
    return `playerInsights.tone.${insight.list}`;
  }

  tone(insight: DashboardInsight): string {
    if (insight.list === 'recent') {
      return insight.params['direction'] === 'declined' ? 'declined' : 'improved';
    }
    return insight.list;
  }

  pick(insight: DashboardInsight): void {
    if (insight.player) {
      this.playerPicked.emit({
        key: insight.player.key,
        role: insight.rule === 'partner_above_overall' ? 'partner' : 'opponent',
      });
    } else if (insight.metric_key) {
      this.metricPicked.emit(insight.metric_key);
    }
  }
}
