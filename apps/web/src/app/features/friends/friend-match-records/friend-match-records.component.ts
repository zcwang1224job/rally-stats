import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import {
  MatchRecordDetailResponse,
  MemberMatchRecordsResponse,
} from '../../../core/api/group-member-view.models';
import { MemberMatchDashboardResponse } from '../../../core/api/player-dashboard.models';
import { MatchRecordDetailDialogComponent } from '../../../core/match-record-detail/match-record-detail-dialog.component';
import { NicknameComponent } from '../../../core/nickname/nickname.component';
import { PlayerDashboardComponent } from '../../../core/player-dashboard/player-dashboard.component';
import { AuthService } from '../../auth/auth.service';

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
    TranslatePipe,
    DatePipe,
    MatchRecordDetailDialogComponent,
    NicknameComponent,
    PlayerDashboardComponent,
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
  readonly pageNumbers = computed(() => {
    const totalPages = this.records()?.total_pages ?? 1;
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  });

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
