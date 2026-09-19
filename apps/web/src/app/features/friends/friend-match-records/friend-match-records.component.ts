import { RatioPercentPipe } from '../../../shared/percent/ratio-percent.pipe';
import { Component, inject, signal, viewChild } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { MatchCardComponent } from '../../../shared/match-card/match-card.component';
import { PaginationComponent } from '../../../shared/pagination/pagination.component';
import { ApiError } from '../../../core/api/api-error';
import {
  MatchRecordDetailResponse,
  MemberMatchRecordsResponse,
} from '../../../core/api/group-member-view.models';
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
@Component({
  selector: 'app-friend-match-records',
  imports: [
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

  focusMetric(key: DashboardMetricKey): void {
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
    const details = row.closest('details');
    if (details) {
      details.open = true;
    }
    row.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
    row.setAttribute('tabindex', '-1');
    row.focus({ preventScroll: true });
  }

  // ---- 036 US4: "compare with me" -------------------------------------------
  /** Off until asked for, and fetched at most once per visit: most looks at a
   * friend's records are not a comparison. */
  readonly comparing = signal(false);
  readonly comparison = signal<MatchComparisonResponse | null>(null);
  readonly comparisonLoading = signal(false);
  readonly comparisonFailed = signal(false);
  private comparisonRequested = false;

  toggleComparison(): void {
    this.comparing.update((on) => !on);
    if (!this.comparing() || this.comparisonRequested) {
      return;
    }
    this.comparisonRequested = true;
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

  constructor() {
    this.load(this.page());
    this.loadDashboard();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load(page);
  }

  private load(page: number): void {
    this.errorKey.set(null);
    this.auth.getFriendMatchRecords(this.memberId, page).subscribe({
      next: (response) => this.records.set(response),
      error: (error: ApiError) => {
        this.records.set(null);
        // Refused now (unfriended / sharing turned off since the page
        // opened): nothing of theirs may stay on screen (023 FR-007).
        this.dashboard.set(null);
        this.comparison.set(null);
        this.comparing.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  /** Once per visit — the friend page has no filters, and a page flip does
   * not change what the dashboard covers. A failure is silent on purpose:
   * see the template. */
  private loadDashboard(): void {
    this.auth.getFriendMatchDashboard(this.memberId).subscribe({
      next: (response) => this.dashboard.set(response),
      error: () => this.dashboard.set(null),
    });
  }

  /** Mirrors `match-history.component.ts`'s existing `openDetail()` —
   * same dialog component, same loading/error signal dance, just a
   * different (friend-scoped) source endpoint. */
  openDetail(matchId: string): void {
    this.detail.set(null);
    this.detailLoadError.set(false);
    this.detailLoading.set(true);
    this.detailDialogRef().open();
    this.auth.getFriendMatchRecordDetail(this.memberId, matchId).subscribe({
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
