import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import {
  MatchRecordResultFilter,
  MatchRecordScoreComparison,
  MemberMatchRecordFilters,
  MemberMatchRecordsResponse,
} from '../../../core/api/group-member-view.models';
import { AuthService } from '../../auth/auth.service';

interface RoundTrendPoint {
  round: number;
  x: number;
  y: number;
  winRate: number;
}

interface PerformanceTier {
  icon: string;
  labelKey: string;
}

const RANK_MEDALS = ['🥇', '🥈', '🥉'];

/** US5 (FR-017~020): 會員頁面「對戰紀錄」——跨團已完成比賽 + 彙總勝負
 * 統計，僅登入會員可見（路由層由既有 member 功能區塊之登入檢查涵蓋）。
 * 篩選（對手/隊友暱稱、勝負、日期、輪次、比分）交由後端計算，所有統計卡
 * 片與圖表都反映篩選後的完整結果集，而非僅目前頁面。 */
@Component({
  selector: 'app-match-history',
  imports: [TranslatePipe, ReactiveFormsModule, DatePipe],
  templateUrl: './match-history.component.html',
  styleUrl: './match-history.component.scss',
})
export class MatchHistoryComponent {
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);

  readonly records = signal<MemberMatchRecordsResponse | null>(null);
  readonly errorKey = signal<string | null>(null);
  readonly page = signal(1);
  readonly pageNumbers = computed(() => {
    const totalPages = this.records()?.total_pages ?? 1;
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  });

  readonly filterForm = this.fb.nonNullable.group({
    opponent1: [''],
    opponent2: [''],
    partner: [''],
    result: [''],
    date_from: [''],
    date_to: [''],
    round_from: [''],
    round_to: [''],
    self_score_cmp: [''],
    self_score: [''],
    opponent_score_cmp: [''],
    opponent_score: [''],
  });

  private readonly appliedFilters = signal<MemberMatchRecordFilters>({});
  readonly hasActiveFilters = computed(
    () => Object.keys(this.appliedFilters()).length > 0,
  );

  /** Win/loss donut's CSS conic-gradient stops. Falls back to a flat muted
   * ring when there's nothing to show yet, so an empty result never
   * renders as a misleading "100% win" circle. */
  readonly winLossGradient = computed(() => {
    const r = this.records();
    if (!r || r.total_matches === 0) {
      return 'conic-gradient(var(--color-border) 0 100%)';
    }
    const winPercent = r.win_rate * 100;
    return (
      `conic-gradient(var(--color-brand-accent) 0 ${winPercent}%, ` +
      `var(--color-danger) ${winPercent}% 100%)`
    );
  });

  /** Round-by-round win-rate trend, laid out on a 0..100 x 0..100 viewBox —
   * x spaced evenly across however many round buckets came back, y
   * inverted (100% win rate at the top, y=0). */
  readonly roundTrendPoints = computed<RoundTrendPoint[]>(() => {
    const buckets = this.records()?.round_win_rates ?? [];
    if (buckets.length === 0) {
      return [];
    }
    const step = buckets.length > 1 ? 100 / (buckets.length - 1) : 0;
    return buckets.map((bucket, index) => ({
      round: bucket.round_number,
      x: buckets.length > 1 ? index * step : 50,
      y: 100 - bucket.win_rate * 100,
      winRate: bucket.win_rate,
    }));
  });

  readonly roundTrendPolyline = computed(() =>
    this.roundTrendPoints()
      .map((point) => `${point.x},${point.y}`)
      .join(' '),
  );

  /** Same line, closed down to the baseline — fills the area under the
   * trend line for a "broadcast graphic" feel instead of a bare line. */
  readonly roundTrendAreaPoints = computed(() => {
    const points = this.roundTrendPoints();
    if (points.length === 0) {
      return '';
    }
    const line = points.map((point) => `${point.x},${point.y}`).join(' ');
    const lastX = points[points.length - 1].x;
    return `0,100 ${line} ${lastX},100`;
  });

  /** A lightweight "athlete rank" read on the member's win rate — purely a
   * motivational framing device (no gameplay effect), gated on having
   * played at least once so a brand-new member doesn't get told they're
   * "蓄勢待發" off a 0-match sample. */
  readonly performanceTier = computed<PerformanceTier | null>(() => {
    const r = this.records();
    if (!r || r.total_matches === 0) {
      return null;
    }
    const rate = r.win_rate;
    if (rate >= 0.7) {
      return { icon: '🏆', labelKey: 'member.matchHistory.tier.elite' };
    }
    if (rate >= 0.5) {
      return { icon: '🔥', labelKey: 'member.matchHistory.tier.strong' };
    }
    if (rate >= 0.3) {
      return { icon: '📈', labelKey: 'member.matchHistory.tier.rising' };
    }
    return { icon: '💪', labelKey: 'member.matchHistory.tier.building' };
  });

  constructor() {
    this.load(this.page());
  }

  applyFilters(): void {
    this.page.set(1);
    this.load(1);
  }

  clearFilters(): void {
    this.filterForm.reset({
      opponent1: '',
      opponent2: '',
      partner: '',
      result: '',
      date_from: '',
      date_to: '',
      round_from: '',
      round_to: '',
      self_score_cmp: '',
      self_score: '',
      opponent_score_cmp: '',
      opponent_score: '',
    });
    this.applyFilters();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load(page);
  }

  private load(page: number): void {
    const raw = this.filterForm.getRawValue();
    const filters: MemberMatchRecordFilters = {
      opponent1: raw.opponent1 || undefined,
      opponent2: raw.opponent2 || undefined,
      partner: raw.partner || undefined,
      result: (raw.result || undefined) as MatchRecordResultFilter | undefined,
      date_from: raw.date_from || undefined,
      date_to: raw.date_to || undefined,
      round_from: raw.round_from ? Number(raw.round_from) : undefined,
      round_to: raw.round_to ? Number(raw.round_to) : undefined,
      self_score_cmp: (raw.self_score_cmp || undefined) as MatchRecordScoreComparison | undefined,
      self_score: raw.self_score ? Number(raw.self_score) : undefined,
      opponent_score_cmp: (raw.opponent_score_cmp || undefined) as
        | MatchRecordScoreComparison
        | undefined,
      opponent_score: raw.opponent_score ? Number(raw.opponent_score) : undefined,
    };
    this.appliedFilters.set(filters);
    this.auth.getMatchRecords(page, filters).subscribe({
      next: (response) => this.records.set(response),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  /** Medal for the top 3 rows of the opponent leaderboard, plain rank
   * number below that. */
  rankBadge(index: number): string {
    return RANK_MEDALS[index] ?? String(index + 1);
  }
}
