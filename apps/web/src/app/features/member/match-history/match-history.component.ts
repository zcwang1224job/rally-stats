import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { InviteCandidateStatus } from '../../../core/api/friend.models';
import {
  BenchmarkGroupOption,
  GroupBenchmarkResponse,
} from '../../../core/api/group-benchmark.models';
import {
  MatchRecordDetailResponse,
  MatchRecordResultFilter,
  MatchRecordScoreComparison,
  MatchupRecord,
  MemberMatchRecordFilters,
  MemberMatchRecordsResponse,
} from '../../../core/api/group-member-view.models';
import {
  DashboardInsights,
  DashboardMetricKey,
  MemberMatchDashboardResponse,
} from '../../../core/api/player-dashboard.models';
import {
  getBenchmarkGroup,
  setBenchmarkGroup,
} from '../../../core/benchmark-group-preference';
import { MatchRecordDetailDialogComponent } from '../../../core/match-record-detail/match-record-detail-dialog.component';
import {
  MatchupRecordsComponent,
  MatchupRole,
} from '../../../core/matchup-records/matchup-records.component';
import { NicknameComponent } from '../../../core/nickname/nickname.component';
import { PlayerDashboardComponent } from '../../../core/player-dashboard/player-dashboard.component';
import { PlayerInsightsComponent } from '../../../core/player-insights/player-insights.component';
import { AddFriendButtonComponent } from '../../../shared/add-friend-button/add-friend-button.component';
import { AuthService } from '../../auth/auth.service';
import { MatchMode } from '../../group-admin/group-admin.models';
import { GroupBenchmarkComponent } from './group-benchmark/group-benchmark.component';
import { FriendsService } from '../../friends/friends.service';

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

/** US5 (FR-017~020): 會員頁面「對戰紀錄」——跨團已完成比賽 + 彙總勝負
 * 統計，僅登入會員可見（路由層由既有 member 功能區塊之登入檢查涵蓋）。
 * 篩選（對手/隊友暱稱、勝負、日期、輪次、比分）交由後端計算，所有統計卡
 * 片與圖表都反映篩選後的完整結果集，而非僅目前頁面。 */
@Component({
  selector: 'app-match-history',
  imports: [
    TranslatePipe,
    ReactiveFormsModule,
    DatePipe,
    MatchRecordDetailDialogComponent,
    NicknameComponent,
    AddFriendButtonComponent,
    PlayerDashboardComponent,
    PlayerInsightsComponent,
    MatchupRecordsComponent,
    GroupBenchmarkComponent,
  ],
  templateUrl: './match-history.component.html',
  styleUrl: './match-history.component.scss',
})
export class MatchHistoryComponent {
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  private readonly friends = inject(FriendsService);

  /** 026-match-record-friend-invite: the viewer's own member_id, so their
   * own row never renders an "加好友" entry (FR-003). */
  private readonly selfMemberId = this.auth.getCachedMemberId();

  /** Batched relationship + eligibility status for every other member
   * visible in the current page of match records (research.md #2) —
   * re-fetched whenever `records` reloads. */
  readonly inviteCandidates = signal<Map<string, InviteCandidateStatus>>(new Map());

  private readonly detailDialogRef =
    viewChild.required<MatchRecordDetailDialogComponent>('detailDialog');
  /** 036 FR-010: an insight sentence jumps to the card it is about. Optional —
   * the dashboard only exists once the records have loaded. */
  private readonly dashboardRef = viewChild(PlayerDashboardComponent);

  focusMetric(key: DashboardMetricKey): void {
    this.dashboardRef()?.focusMetric(key);
  }

  readonly detail = signal<MatchRecordDetailResponse | null>(null);
  readonly detailLoading = signal(false);
  readonly detailLoadError = signal(false);

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
    match_mode: [''],
  });

  private readonly appliedFilters = signal<MemberMatchRecordFilters>({});

  /** 034-clutch-points-player-dashboard: the cross-match dashboard, always
   * over the same filters as `records`. */
  readonly dashboard = signal<MemberMatchDashboardResponse | null>(null);
  readonly dashboardLoading = signal(false);
  readonly dashboardFailed = signal(false);
  /** The landing court draws singles lines only when every match is one. */
  readonly singlesOnly = computed(() => this.appliedFilters().match_mode === 'singles');
  private dashboardFiltersKey: string | null = null;
  /** `load()` always builds the full filter object, most of it `undefined` —
   * so count values, not keys (counting keys made this true after the very
   * first load). 036 relies on it: in-group sentences only join the summary
   * while no filter is active (FR-034). */
  readonly hasActiveFilters = computed(() =>
    Object.values(this.appliedFilters()).some((value) => value !== undefined),
  );

  // ---- 036 US3: the in-group comparison (research.md Decision 9) ----------
  /** null until asked for: the most expensive request on the page is only
   * made for a member who uses it — on opening the block, or straight away
   * when a group was chosen on an earlier visit (its sentences belong in the
   * summary, FR-033). */
  readonly benchmarkGroups = signal<BenchmarkGroupOption[] | null>(null);
  readonly benchmarkGroupId = signal<string | null>(null);
  readonly benchmark = signal<GroupBenchmarkResponse | null>(null);
  readonly benchmarkLoading = signal(false);
  readonly benchmarkFailed = signal(false);
  private benchmarkStarted = false;
  private benchmarkRequest = 0;

  /** THE rule for which summary is shown, and the only one (FR-033, FR-034):
   * the benchmark response's — my unfiltered summary with the in-group source
   * merged in by the backend — while it is loaded and no filter is active;
   * otherwise the dashboard's own. Nothing is merged, ranked or thresholded
   * here. */
  readonly summaryInsights = computed<DashboardInsights | null>(() => {
    const inGroup = this.benchmark();
    return inGroup && !this.hasActiveFilters()
      ? inGroup.insights
      : (this.dashboard()?.insights ?? null);
  });
  readonly benchmarkPending = computed(() => this.benchmarkLoading() && !this.hasActiveFilters());
  readonly benchmarkOmittedByFilters = computed(
    () => this.benchmarkGroupId() !== null && this.hasActiveFilters(),
  );

  /** Opening the block, or a remembered group: load my groups, then the one
   * to compare within — the remembered one if it is still mine to open, else
   * the one with most of my matches (FR-027). Once per visit. */
  startBenchmark(): void {
    if (this.benchmarkStarted) {
      return;
    }
    this.benchmarkStarted = true;
    this.auth.getBenchmarkGroups().subscribe({
      next: ({ groups }) => {
        this.benchmarkGroups.set(groups);
        const remembered = getBenchmarkGroup(this.selfMemberId);
        const pick = groups.find((group) => group.group_id === remembered) ?? groups[0];
        if (pick) {
          this.selectBenchmarkGroup(pick.group_id);
        }
      },
      error: () => {
        this.benchmarkGroups.set([]);
        this.benchmarkFailed.set(true);
      },
    });
  }

  selectBenchmarkGroup(groupId: string): void {
    setBenchmarkGroup(this.selfMemberId, groupId);
    this.benchmarkGroupId.set(groupId);
    this.benchmark.set(null);
    this.benchmarkLoading.set(true);
    this.benchmarkFailed.set(false);
    const request = ++this.benchmarkRequest;
    this.auth.getGroupBenchmark(groupId).subscribe({
      next: (response) => {
        if (request !== this.benchmarkRequest) {
          return; // a later choice already superseded this one
        }
        this.benchmark.set(response);
        this.benchmarkLoading.set(false);
      },
      error: () => {
        if (request !== this.benchmarkRequest) {
          return;
        }
        // Stays inside its own block: the summary falls back to the
        // dashboard's, and nothing else on the page notices (FR-007).
        this.benchmarkLoading.set(false);
        this.benchmarkFailed.set(true);
      },
    });
  }

  /** 036 US2: the partner or opponent whose row was clicked. Sent as an exact
   * `partner_key` / `opponent_key`, alongside whatever the form holds — the
   * two kinds of filter combine and clear independently. */
  readonly pickedPlayer = signal<{ role: MatchupRole; record: MatchupRecord } | null>(null);

  pickPlayer(role: MatchupRole, record: MatchupRecord): void {
    this.pickedPlayer.set({ role, record });
    this.applyFilters();
  }

  clearPickedPlayer(): void {
    this.pickedPlayer.set(null);
    this.applyFilters();
  }

  /** FR-010: a matchup sentence in the summary leads to that player's row. */
  focusMatchup(target: { key: string; role: MatchupRole }): void {
    const row = document.getElementById(`matchup-${target.role}-${target.key}`);
    if (!row) {
      return;
    }
    const details = row.closest('details');
    if (details) {
      details.open = true;
    }
    row.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
    (row.querySelector('button') ?? row).focus?.({ preventScroll: true });
  }

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
    this.pickedPlayer.set(null);
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
      match_mode: '',
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
      match_mode: (raw.match_mode || undefined) as MatchMode | undefined,
      partner_key: this.pickedKey('partner'),
      opponent_key: this.pickedKey('opponent'),
    };
    this.appliedFilters.set(filters);
    this.loadDashboard(filters);
    this.auth.getMatchRecords(page, filters).subscribe({
      next: (response) => {
        this.records.set(response);
        this.loadInviteCandidates(response);
      },
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  private pickedKey(role: MatchupRole): string | undefined {
    const picked = this.pickedPlayer();
    return picked?.role === role ? picked.record.player_key : undefined;
  }

  /** The dashboard reads every match's point log, so it is fetched when the
   * FILTERS change — never for a mere page flip. Keyed on the filters that
   * were actually sent rather than on which button was pressed, because
   * `load()` re-reads the form on a page flip too: whatever path changed
   * the list's filters, the dashboard follows. */
  private loadDashboard(filters: MemberMatchRecordFilters): void {
    const key = JSON.stringify(filters);
    if (key === this.dashboardFiltersKey) {
      return;
    }
    this.dashboardFiltersKey = key;
    this.dashboardLoading.set(true);
    this.dashboardFailed.set(false);
    this.auth.getMatchDashboard(filters).subscribe({
      next: (response) => {
        if (getBenchmarkGroup(this.selfMemberId)) {
          this.startBenchmark(); // after the dashboard, never ahead of it
        }
        if (key !== this.dashboardFiltersKey) {
          return; // a newer request has been sent since
        }
        this.dashboard.set(response);
        this.dashboardLoading.set(false);
      },
      error: () => {
        if (key !== this.dashboardFiltersKey) {
          return;
        }
        this.dashboard.set(null);
        this.dashboardFailed.set(true);
        this.dashboardLoading.set(false);
        this.dashboardFiltersKey = null; // let the next load retry
      },
    });
  }

  /** 026-match-record-friend-invite: collects every other member visible
   * in this page's matches (excluding self and Guests, whose participants
   * have no member_id) and looks up their "加好友" status in one batch
   * call. */
  private loadInviteCandidates(response: MemberMatchRecordsResponse): void {
    const memberIds = new Set<string>();
    for (const match of response.matches) {
      for (const p of [...match.team_a, ...match.team_b]) {
        if (p.member_id && p.member_id !== this.selfMemberId) {
          memberIds.add(p.member_id);
        }
      }
    }
    if (memberIds.size === 0) {
      this.inviteCandidates.set(new Map());
      return;
    }
    this.friends.getInviteCandidatesStatus([...memberIds]).subscribe({
      next: (result) => {
        this.inviteCandidates.set(new Map(result.candidates.map((c) => [c.member_id, c])));
      },
      error: () => this.inviteCandidates.set(new Map()),
    });
  }

  inviteCandidateFor(memberId: string): InviteCandidateStatus | undefined {
    return this.inviteCandidates().get(memberId);
  }

  /** 016-match-score-timeline: opens the match detail dialog via
   * `AuthService.getMatchRecordDetail()` — the "ever a member" endpoint,
   * NOT `GroupMemberViewService`'s active-membership one (research.md
   * #1/#4), since this list already includes matches from groups the
   * member may no longer be active in. */
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
