import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../../core/api/api-error';
import { MemberGroupHistoryResponse } from '../../../../core/api/friend.models';
import {
  MatchRecordDetailResponse,
  MatchRecordSummary,
} from '../../../../core/api/group-member-view.models';
import { MatchRecordDetailDialogComponent } from '../../../../core/match-record-detail/match-record-detail-dialog.component';
import { AuthService } from '../../../auth/auth.service';
import { FriendsService } from '../../../friends/friends.service';

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

/** 014-member-groups-history follow-up: two independent sections on one
 * page. "我的戰績" (`my_stats`) is this member's own performance in the
 * group — a win-rate donut, round-trend chart, and opponent leaderboard,
 * always reflecting the member's FULL history here, styled after the
 * cross-group "對戰紀錄" page (`member/match-history`). "對戰紀錄"
 * (`matches`) is the group's own shared match history — every completed
 * match, any participant — searchable by any player's nickname; this list
 * is NOT scoped to the viewer's own games (corrected after user feedback:
 * an earlier revision incorrectly narrowed it to "my matches only").
 * Reachable even for a group the member has since left or been kicked
 * from (FR-006). */
@Component({
  selector: 'app-group-history',
  imports: [TranslatePipe, ReactiveFormsModule, DatePipe, RouterLink, MatchRecordDetailDialogComponent],
  templateUrl: './group-history.component.html',
  styleUrl: './group-history.component.scss',
})
export class GroupHistoryComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly friends = inject(FriendsService);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);

  private readonly groupId = this.route.snapshot.paramMap.get('groupId')!;

  private readonly detailDialogRef =
    viewChild.required<MatchRecordDetailDialogComponent>('detailDialog');
  readonly detail = signal<MatchRecordDetailResponse | null>(null);
  readonly detailLoading = signal(false);
  readonly detailLoadError = signal(false);

  readonly history = signal<MemberGroupHistoryResponse | null>(null);
  readonly errorKey = signal<string | null>(null);
  readonly page = signal(1);
  readonly pageNumbers = computed(() => {
    const totalPages = this.history()?.total_pages ?? 1;
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  });

  readonly filterForm = this.fb.nonNullable.group({
    nickname: [''],
  });

  readonly hasActiveFilters = computed(() => this.filterForm.controls.nickname.value !== '');

  /** Win/loss donut's CSS conic-gradient stops — same convention as the
   * cross-group match-history page. Always reflects `my_stats` (personal,
   * unfiltered). */
  readonly winLossGradient = computed(() => {
    const stats = this.history()?.my_stats;
    if (!stats || stats.total_matches === 0) {
      return 'conic-gradient(var(--color-border) 0 100%)';
    }
    const winPercent = stats.win_rate * 100;
    return (
      `conic-gradient(var(--color-brand-accent) 0 ${winPercent}%, ` +
      `var(--color-danger) ${winPercent}% 100%)`
    );
  });

  readonly roundTrendPoints = computed<RoundTrendPoint[]>(() => {
    const buckets = this.history()?.my_stats.round_win_rates ?? [];
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

  readonly roundTrendAreaPoints = computed(() => {
    const points = this.roundTrendPoints();
    if (points.length === 0) {
      return '';
    }
    const line = points.map((point) => `${point.x},${point.y}`).join(' ');
    const lastX = points[points.length - 1].x;
    return `0,100 ${line} ${lastX},100`;
  });

  readonly performanceTier = computed<PerformanceTier | null>(() => {
    const stats = this.history()?.my_stats;
    if (!stats || stats.total_matches === 0) {
      return null;
    }
    const rate = stats.win_rate;
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
    this.filterForm.reset({ nickname: '' });
    this.applyFilters();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load(page);
  }

  private load(page: number): void {
    const nickname = this.filterForm.controls.nickname.value || undefined;
    this.friends.getMemberGroupHistory(this.groupId, page, nickname).subscribe({
      next: (response) => this.history.set(response),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  rankBadge(index: number): string {
    return RANK_MEDALS[index] ?? String(index + 1);
  }

  /** The winning side's player names, joined. */
  winnerNames(match: MatchRecordSummary): string {
    const winners = match.winner_team === 'A' ? match.team_a : match.team_b;
    return winners.map((p) => p.nickname).join('、');
  }

  /** 016-match-score-timeline: opens the match detail dialog via
   * `AuthService.getMatchRecordDetail()` — the SAME "ever a member"
   * endpoint `member/match-history` uses, deliberately NOT
   * `GroupMemberViewService`'s active-membership one (research.md #1/#4).
   * This page exists precisely so a member who has left/been kicked from
   * the group can still review its history (014) — using the
   * active-membership endpoint here would silently break that for exactly
   * the members this page is for (previously the I1 finding). */
  openDetail(matchId: string): void {
    this.detail.set(null);
    this.detailLoadError.set(false);
    this.detailLoading.set(true);
    this.detailDialogRef().open();
    this.auth.getMatchRecordDetail(matchId).subscribe({
      next: (response) => {
        this.detail.set(response);
        this.detailLoading.set(false);
      },
      error: () => {
        this.detailLoadError.set(true);
        this.detailLoading.set(false);
      },
    });
  }
}
