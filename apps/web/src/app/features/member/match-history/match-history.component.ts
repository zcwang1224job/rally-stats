import { Team } from '../../../core/api/court-live-state.models';
import { ActivitySummary } from '../../../core/api/sport.models';
import { DashboardSectionsResponse } from '../../../core/api/sports.service';
import { SectionOutletComponent } from '../../../sports/section-outlet/section-outlet.component';
import { LEGACY_SPORT_TYPE } from '../../../sports/sport-type-module';
import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { TranslatePipe } from '@ngx-translate/core';
import { RecordHeroComponent } from '../../../shared/record-hero/record-hero.component';
import { MatchCardComponent } from '../../../shared/match-card/match-card.component';
import { RoundTrendChartComponent } from '../../../shared/round-trend-chart/round-trend-chart.component';
import { PaginationComponent } from '../../../shared/pagination/pagination.component';
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
  MemberMatchRecordSummary,
  MemberMatchRecordsResponse,
} from '../../../core/api/group-member-view.models';
import { ShareCardContext } from '../../../core/match-share-card/share-card.models';
import {
  DashboardInsights,
  DashboardMetricKey,
  MemberMatchDashboardResponse,
} from '../../../core/api/player-dashboard.models';
import {
  getBenchmarkGroup,
  setBenchmarkGroup,
} from '../../../core/benchmark-group-preference';
import { localDayStart } from '../../../core/local-day';
import { SectionAccordion } from '../../../core/section-accordion/section-accordion';
import { MatchRecordDetailDialogComponent } from '../../../core/match-record-detail/match-record-detail-dialog.component';
import {
  MatchupRecordsComponent,
  MatchupRole,
} from '../../../core/matchup-records/matchup-records.component';
import { PlayerDashboardComponent } from '../../../core/player-dashboard/player-dashboard.component';
import { PlayerInsightsComponent } from '../../../core/player-insights/player-insights.component';
import { AuthService } from '../../auth/auth.service';
import { MatchMode } from '../../group-admin/group-admin.models';
import { GroupBenchmarkComponent } from './group-benchmark/group-benchmark.component';
import { FriendsService } from '../../friends/friends.service';

/** US5 (FR-017~020): 會員頁面「對戰紀錄」——跨團已完成比賽 + 彙總勝負
 * 統計，僅登入會員可見（路由層由既有 member 功能區塊之登入檢查涵蓋）。
 * 篩選（對手/隊友暱稱、勝負、日期、輪次、比分）交由後端計算，所有統計卡
 * 片與圖表都反映篩選後的完整結果集，而非僅目前頁面。 */
/** The two tabs under the summary. */
export type MatchHistoryTab = 'matches' | 'stats';

/** The page's big sections, run as an accordion (one open at a time). */
export type MatchHistorySection =
  | 'insights'
  | 'dashboard'
  | 'benchmark'
  | 'roundTrend'
  | 'partners'
  | 'opponents';

@Component({
  selector: 'app-match-history',
  imports: [
    RecordHeroComponent,
    MatchCardComponent,
    RoundTrendChartComponent,
    PaginationComponent,
    TranslatePipe,
    ReactiveFormsModule,
    MatchRecordDetailDialogComponent,
    PlayerDashboardComponent,
    SectionOutletComponent,
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
  private readonly matchList = viewChild<ElementRef<HTMLElement>>('matchList');

  /** The matches first — what most visits are for; the analysis one tap
   * away. The filters apply to both. */
  readonly activeTab = signal<MatchHistoryTab>('matches');

  /** The big sections (on the analysis tab), one open at a time, all folded
   * on arrival. */
  readonly sections = new SectionAccordion<MatchHistorySection>();

  focusMetric(key: DashboardMetricKey): void {
    this.sections.openNow('dashboard');
    this.dashboardRef()?.focusMetric(key);
  }

  readonly detail = signal<MatchRecordDetailResponse | null>(null);
  readonly detailLoading = signal(false);
  readonly detailLoadError = signal(false);
  readonly shareContext = signal<ShareCardContext | null>(null);

  readonly records = signal<MemberMatchRecordsResponse | null>(null);
  readonly errorKey = signal<string | null>(null);
  readonly page = signal(1);

  readonly filterForm = this.fb.nonNullable.group({
    opponent1: [''],
    opponent2: [''],
    partner: [''],
    result: [''],
    // the viewer's LOCAL calendar days (`YYYY-MM-DD`), both ends inclusive —
    // `load()` turns them into the instants the API takes
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

  /** 043 FR-026: the activities I have played. With more than one, each is
   * a tab and nothing is ever added up across them; the chosen one filters
   * the whole page. A net rally activity keeps the dashboard below; the
   * others show the sections their sport type lays out. */
  readonly activities = signal<ActivitySummary[]>([]);
  readonly selectedSport = signal<string | null>(null);
  readonly selectedActivity = computed(
    () => this.activities().find((a) => a.filter_value === this.selectedSport()) ?? null,
  );
  readonly usesSections = computed(() => {
    const activity = this.selectedActivity();
    return activity !== null && activity.sport.type_key !== LEGACY_SPORT_TYPE;
  });
  readonly sectionsDashboard = signal<DashboardSectionsResponse | null>(null);
  readonly sectionsLoading = signal(false);
  readonly sectionsFailed = signal(false);
  private sectionsKey: string | null = null;

  selectActivity(filterValue: string): void {
    if (filterValue === this.selectedSport()) {
      return;
    }
    this.selectedSport.set(filterValue);
    this.pickedPlayer.set(null);
    this.page.set(1);
    this.load(1);
  }

  private loadActivities(): void {
    this.auth.getActivities().subscribe({
      next: (activities) => {
        this.activities.set(activities);
        // FR-026: several activities are tabs; one activity is shown as
        // itself — unless it is net rally, which the page shows already.
        const first = activities[0];
        const showFirst =
          activities.length > 1 || (first !== undefined && first.sport.type_key !== LEGACY_SPORT_TYPE);
        if (showFirst && this.selectedSport() === null) {
          this.selectActivity(first.filter_value);
        }
      },
      // Without the list the page stays on net rally, as before 043.
      error: () => this.activities.set([]),
    });
  }

  private loadSections(filters: MemberMatchRecordFilters): void {
    const key = JSON.stringify(filters);
    if (key === this.sectionsKey) {
      return;
    }
    this.sectionsKey = key;
    this.dashboardFiltersKey = null;
    this.sectionsLoading.set(true);
    this.sectionsFailed.set(false);
    this.auth.getDashboardSections(filters).subscribe({
      next: (response) => {
        if (key !== this.sectionsKey) {
          return;
        }
        this.sectionsDashboard.set(response);
        this.sectionsLoading.set(false);
      },
      error: () => {
        if (key !== this.sectionsKey) {
          return;
        }
        this.sectionsDashboard.set(null);
        this.sectionsFailed.set(true);
        this.sectionsLoading.set(false);
        this.sectionsKey = null;
      },
    });
  }
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
    // 043: the activity tab is not a filter the member set.
    Object.entries(this.appliedFilters()).some(
      ([key, value]) => key !== 'sport' && value !== undefined,
    ),
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
    // The row click is "show me our matches": they are on the other tab.
    this.activeTab.set('matches');
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
    this.sections.openNow(target.role === 'partner' ? 'partners' : 'opponents');
    row.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
    (row.querySelector('button') ?? row).focus?.({ preventScroll: true });
  }

  /** Win/loss donut's CSS conic-gradient stops. Falls back to a flat muted
   * ring when there's nothing to show yet, so an empty result never
   * renders as a misleading "100% win" circle. */

  constructor() {
    this.load(this.page());
    this.loadActivities();
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
    this.load(page, { scrollToList: true });
  }

  /** Brings the match list's top edge into view (after a page flip). */
  scrollToMatchList(): void {
    this.matchList()?.nativeElement.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
  }

  /** `scrollToList`: a page flip is tapped from the pagination under the
   * list — without it a phone user lands at the BOTTOM of the new page. The
   * old list stays rendered until the response arrives, so its top edge is
   * already where the new one will be. */
  private load(page: number, { scrollToList = false } = {}): void {
    const raw = this.filterForm.getRawValue();
    const filters: MemberMatchRecordFilters = {
      opponent1: raw.opponent1 || undefined,
      opponent2: raw.opponent2 || undefined,
      partner: raw.partner || undefined,
      result: (raw.result || undefined) as MatchRecordResultFilter | undefined,
      // A half-open range of instants: an inclusive "to" day becomes "before
      // the start of the day after". Sending the bare dates had the server
      // compare them with each match's UTC date, so a match finished before
      // 08:00 Taipei time was filed under the previous day.
      ended_from: localDayStart(raw.date_from),
      ended_before: localDayStart(raw.date_to, 1),
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
      sport: this.selectedSport() ?? undefined,
    };
    this.appliedFilters.set(filters);
    this.loadDashboard(filters);
    // The first load races the activity tab's: only the latest answer counts.
    const request = ++this.recordsRequest;
    this.auth.getMatchRecords(page, filters).subscribe({
      next: (response) => {
        if (request !== this.recordsRequest) {
          return;
        }
        this.records.set(response);
        this.loadInviteCandidates(response);
        if (scrollToList) {
          this.scrollToMatchList();
        }
      },
      error: (error: ApiError) => {
        if (request === this.recordsRequest) {
          this.errorKey.set(error.i18nKey);
        }
      },
    });
  }

  private recordsRequest = 0;

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
    if (this.usesSections()) {
      this.loadSections(filters);
      return;
    }
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

  /** Bound for the match card's add-friend lookup. */
  readonly candidateLookup = (memberId: string) => this.inviteCandidateFor(memberId);

  /** 016-match-score-timeline: opens the match detail dialog via
   * `AuthService.getMatchRecordDetail()` — the "ever a member" endpoint,
   * NOT `GroupMemberViewService`'s active-membership one (research.md
   * #1/#4), since this list already includes matches from groups the
   * member may no longer be active in. */
  openDetail(match: MemberMatchRecordSummary): void {
    // 040-match-share-card FR-016: this is the viewer's own match list, so
    // the share card takes their side. Which side is read off this row
    // (won + winner_team), never matched against the logged-in member.
    // 043: a draw has no winner to read my side off, so my side comes
    // from the roster (team A's if this member is on neither, e.g. an
    // older list without member ids).
    const me = this.auth.getCachedMemberId();
    const onTeam = (team: readonly { member_id?: string | null }[]) =>
      me !== null && team.some((p) => p.member_id === me);
    let myTeam: Team;
    if (match.winner_team === 'D') {
      myTeam = onTeam(match.team_b) ? 'B' : 'A';
    } else {
      myTeam = match.won ? match.winner_team : match.winner_team === 'A' ? 'B' : 'A';
    }
    this.shareContext.set({
      groupName: match.group_name,
      perspective: { kind: 'mine', myTeam },
    });
    this.detail.set(null);
    this.detailLoadError.set(false);
    this.detailLoading.set(true);
    this.detailDialogRef().open();
    this.auth.getMatchRecordDetail(match.match_id).subscribe({
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
