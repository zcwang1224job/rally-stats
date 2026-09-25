import { ActivitySummary } from '../../../core/api/sport.models';
import { DashboardSectionsResponse } from '../../../core/api/sports.service';
import { SectionOutletComponent } from '../../../sports/section-outlet/section-outlet.component';
import { LEGACY_SPORT_TYPE } from '../../../sports/sport-type-module';
import { RatioPercentPipe } from '../../../shared/percent/ratio-percent.pipe';
import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { MatchCardComponent } from '../../../shared/match-card/match-card.component';
import { PaginationComponent } from '../../../shared/pagination/pagination.component';
import { ApiError } from '../../../core/api/api-error';
import {
  MatchRecordDetailResponse,
  MemberMatchRecordSummary,
  MemberMatchRecordsResponse,
} from '../../../core/api/group-member-view.models';
import { ShareCardContext } from '../../../core/match-share-card/share-card.models';
import {
  DashboardMetricKey,
  MemberMatchDashboardResponse,
} from '../../../core/api/player-dashboard.models';
import { MatchComparisonResponse } from '../../../core/api/match-comparison.models';
import { MatchRecordDetailDialogComponent } from '../../../core/match-record-detail/match-record-detail-dialog.component';
import {
  MatchupRecordsComponent,
  MatchupRole,
} from '../../../core/matchup-records/matchup-records.component';
import { PlayerDashboardComponent } from '../../../core/player-dashboard/player-dashboard.component';
import { PlayerInsightsComponent } from '../../../core/player-insights/player-insights.component';
import { AuthService } from '../../auth/auth.service';
import { SectionAccordion } from '../../../core/section-accordion/section-accordion';
import { FriendComparisonComponent } from './friend-comparison/friend-comparison.component';

/** 023-view-friend-match-records US1/US2: a deliberately thin sibling of
 * `member/match-history/match-history.component` — same list/pagination/
 * detail-dialog shape, but reading a FRIEND's records
 * (`AuthService.getFriendMatchRecords()`/`getFriendMatchRecordDetail()`,
 * both backed by 022's already-authorized endpoints) and, per spec.md
 * Assumptions (research.md #1), deliberately WITHOUT the advanced filter
 * form, round-trend chart, or opponent leaderboard.
 *
 * FR-008: every load — including pagination — re-calls the server; the
 * component never remembers "was I allowed last time" and skips the call. */
/** The page's big sections, run as an accordion (one open at a time). */
export type FriendRecordsSection = 'comparison' | 'insights' | 'dashboard' | 'partners' | 'opponents';

@Component({
  selector: 'app-friend-match-records',
  imports: [
    SectionOutletComponent,
    RatioPercentPipe,
    MatchCardComponent,
    PaginationComponent,
    TranslatePipe,
    MatchRecordDetailDialogComponent,
    PlayerDashboardComponent,
    PlayerInsightsComponent,
    MatchupRecordsComponent,
    FriendComparisonComponent,
  ],
  templateUrl: './friend-match-records.component.html',
  styleUrl: './friend-match-records.component.scss',
})
export class FriendMatchRecordsComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly auth = inject(AuthService);

  private readonly memberId = this.route.snapshot.paramMap.get('memberId')!;
  /** research.md #2: display-only, carried from the friend-list link;
   * MUST NOT be treated as an authorization signal — falls back to a
   * generic title (via the template) when absent, e.g. a direct URL
   * visit (spec.md Edge Case #1). */
  readonly nickname = signal(this.route.snapshot.queryParamMap.get('nickname'));

  readonly records = signal<MemberMatchRecordsResponse | null>(null);
  readonly errorKey = signal<string | null>(null);
  readonly page = signal(1);
  /** 034 US5: the friend's technique dashboard — same privacy gate as the
   * records, checked by the server on its own request. */
  readonly dashboard = signal<MemberMatchDashboardResponse | null>(null);

  /** 036 FR-037 / FR-010: the friend's summary jumps to the friend's cards. */
  private readonly dashboardRef = viewChild(PlayerDashboardComponent);

  /** The big sections, one open at a time, all folded on arrival — the same
   * as on the member's own 對戰紀錄. */
  readonly sections = new SectionAccordion<FriendRecordsSection>();

  focusMetric(key: DashboardMetricKey): void {
    this.sections.openNow('dashboard');
    this.dashboardRef()?.focusMetric(key);
  }

  /** 036 FR-010: a matchup sentence leads to that player's row. The rows are
   * not clickable here (no filters on this page), so the row itself is the
   * landing place. */
  focusMatchup(target: { key: string; role: MatchupRole }): void {
    const row = document.getElementById(`matchup-${target.role}-${target.key}`);
    if (!row) {
      return;
    }
    this.sections.openNow(target.role === 'partner' ? 'partners' : 'opponents');
    row.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
    row.setAttribute('tabindex', '-1');
    row.focus({ preventScroll: true });
  }

  // ---- 036 US4: "compare with me" -------------------------------------------
  /** Off until asked for — the first time its panel is opened — and then
   * fetched at most once per visit: most looks at a friend's records are not
   * a comparison. */
  readonly comparisonRequested = signal(false);
  readonly comparison = signal<MatchComparisonResponse | null>(null);
  readonly comparisonLoading = signal(false);
  readonly comparisonFailed = signal(false);

  onComparisonToggle(open: boolean): void {
    this.sections.toggled('comparison', open);
    if (!open || this.comparisonRequested()) {
      return;
    }
    this.comparisonRequested.set(true);
    this.comparisonLoading.set(true);
    this.auth.getFriendMatchComparison(this.memberId).subscribe({
      next: (response) => {
        this.comparison.set(response);
        this.comparisonLoading.set(false);
      },
      error: () => {
        // A refusal shows up as the page's own alert on the next records
        // request; here it is simply "could not compare".
        this.comparisonLoading.set(false);
        this.comparisonFailed.set(true);
      },
    });
  }


  private readonly detailDialogRef =
    viewChild.required<MatchRecordDetailDialogComponent>('detailDialog');
  readonly detail = signal<MatchRecordDetailResponse | null>(null);
  readonly detailLoading = signal(false);
  readonly detailLoadError = signal(false);
  readonly shareContext = signal<ShareCardContext | null>(null);

  constructor() {
    this.load(this.page());
    this.loadDashboard();
    this.loadActivities();
  }

  /** 043 FR-026: one tab per activity the friend has played; see the
   * member's own match history for the same rule. */
  readonly activities = signal<ActivitySummary[]>([]);
  readonly selectedSport = signal<string | null>(null);
  readonly usesSections = computed(() => {
    const activity = this.activities().find((a) => a.filter_value === this.selectedSport());
    return activity !== undefined && activity.sport.type_key !== LEGACY_SPORT_TYPE;
  });
  readonly sectionsDashboard = signal<DashboardSectionsResponse | null>(null);

  selectActivity(filterValue: string): void {
    if (filterValue === this.selectedSport()) {
      return;
    }
    this.selectedSport.set(filterValue);
    this.page.set(1);
    this.load(1);
    this.loadDashboard();
  }

  private loadActivities(): void {
    this.auth.getFriendActivities(this.memberId).subscribe({
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
      error: () => this.activities.set([]),
    });
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load(page);
  }

  private load(page: number): void {
    this.errorKey.set(null);
    const sport = this.selectedSport();
    const request = sport
      ? this.auth.getFriendMatchRecords(this.memberId, page, sport)
      : this.auth.getFriendMatchRecords(this.memberId, page);
    // The first load races the activity tab's: only the latest answer counts.
    const sequence = ++this.recordsRequest;
    request.subscribe({
      next: (response) => {
        if (sequence === this.recordsRequest) {
          this.records.set(response);
        }
      },
      error: (error: ApiError) => {
        if (sequence !== this.recordsRequest) {
          return;
        }
        this.records.set(null);
        // Refused now (unfriended / sharing turned off since the page
        // opened): nothing of theirs may stay on screen (023 FR-007).
        this.dashboard.set(null);
        this.comparison.set(null);
        this.comparisonRequested.set(false); // asked again if re-opened once allowed
        this.sections.closeAll();
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  /** Once per visit — the friend page has no filters, and a page flip does
   * not change what the dashboard covers. A failure is silent on purpose:
   * see the template. */
  private loadDashboard(): void {
    const sport = this.selectedSport();
    const sequence = ++this.dashboardRequest;
    if (sport && this.usesSections()) {
      this.dashboard.set(null);
      this.auth.getFriendDashboardSections(this.memberId, sport).subscribe({
        next: (response) => {
          if (sequence === this.dashboardRequest) {
            this.sectionsDashboard.set(response);
          }
        },
        error: () => {
          if (sequence === this.dashboardRequest) {
            this.sectionsDashboard.set(null);
          }
        },
      });
      return;
    }
    this.sectionsDashboard.set(null);
    const request = sport
      ? this.auth.getFriendMatchDashboard(this.memberId, sport)
      : this.auth.getFriendMatchDashboard(this.memberId);
    request.subscribe({
      next: (response) => {
        if (sequence === this.dashboardRequest) {
          this.dashboard.set(response);
        }
      },
      error: () => {
        if (sequence === this.dashboardRequest) {
          this.dashboard.set(null);
        }
      },
    });
  }

  private recordsRequest = 0;
  private dashboardRequest = 0;

  /** Mirrors `match-history.component.ts`'s existing `openDetail()` —
   * same dialog component, same loading/error signal dance, just a
   * different (friend-scoped) source endpoint. */
  openDetail(match: MemberMatchRecordSummary): void {
    // 040-match-share-card FR-017: a friend's match is shared neutrally.
    this.shareContext.set({ groupName: match.group_name, perspective: { kind: 'neutral' } });
    this.detail.set(null);
    this.detailLoadError.set(false);
    this.detailLoading.set(true);
    this.detailDialogRef().open();
    this.auth.getFriendMatchRecordDetail(this.memberId, match.match_id).subscribe({
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
