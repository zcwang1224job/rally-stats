import { Component, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { MatchCardComponent } from '../../../shared/match-card/match-card.component';
import { PaginationComponent } from '../../../shared/pagination/pagination.component';
import { ApiError } from '../../../core/api/api-error';
import { InviteCandidateStatus } from '../../../core/api/friend.models';
import {
  GroupMatchRecordsResponse,
  MatchRecordDetailResponse,
} from '../../../core/api/group-member-view.models';
import { MatchRecordDetailDialogComponent } from '../../../core/match-record-detail/match-record-detail-dialog.component';
import { ShareCardContext } from '../../../core/match-share-card/share-card.models';
import { AuthService } from '../../auth/auth.service';
import { FriendsService } from '../../friends/friends.service';
import { GroupMemberViewService } from '../group-member-view.service';

/** US3 (FR-011/012): 團內對戰紀錄——逐場列表，僅限本團，載入時查詢。
 * 016-match-score-timeline US1/US2/US3: 每列點擊開啟比賽詳情彈出視窗——
 * 呼叫本頁本來就已經在用的 `GroupMemberViewService`（見 research.md #4，
 * 刻意不透過任何「依 groupId 有無決定端點」的共用邏輯）。 */
@Component({
  selector: 'app-match-records',
  imports: [
    MatchCardComponent,
    PaginationComponent,
    TranslatePipe,
    MatchRecordDetailDialogComponent,
  ],
  templateUrl: './match-records.component.html',
  styleUrl: './match-records.component.scss',
})
export class MatchRecordsComponent {
  readonly groupId = input.required<string>();
  /** 040-match-share-card: the share card names the group; the shell above
   * has already loaded it. */
  readonly groupName = input.required<string>();

  /** FR-017: in-group records are always shared neutrally. */
  readonly shareContext = computed<ShareCardContext>(() => ({
    groupName: this.groupName(),
    perspective: { kind: 'neutral' },
  }));

  private readonly memberView = inject(GroupMemberViewService);
  private readonly auth = inject(AuthService);
  private readonly friends = inject(FriendsService);

  /** 026-match-record-friend-invite: the viewer's own member_id, so their
   * own row never renders an "加好友" entry (FR-003). */
  private readonly selfMemberId = this.auth.getCachedMemberId();

  /** Batched relationship + eligibility status for every other member
   * visible in the current page (research.md #2). */
  readonly inviteCandidates = signal<Map<string, InviteCandidateStatus>>(new Map());

  readonly records = signal<GroupMatchRecordsResponse | null>(null);
  readonly errorKey = signal<string | null>(null);
  readonly page = signal(1);

  private readonly detailDialogRef =
    viewChild.required<MatchRecordDetailDialogComponent>('detailDialog');
  readonly detail = signal<MatchRecordDetailResponse | null>(null);
  readonly detailLoading = signal(false);
  readonly detailLoadError = signal(false);

  constructor() {
    effect(() => {
      if (!this.groupId()) {
        return;
      }
      this.load(this.page());
    });
  }

  private load(page: number): void {
    this.memberView.getMatchRecords(this.groupId(), page).subscribe({
      next: (response) => {
        this.records.set(response);
        this.loadInviteCandidates(response);
      },
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  /** 026-match-record-friend-invite: collects every other member visible
   * in this page's matches (excluding self and Guests) and looks up their
   * "加好友" status in one batch call — includes teammates, not just
   * opponents (US1 acceptance scenario 2). */
  private loadInviteCandidates(response: GroupMatchRecordsResponse): void {
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

  goToPage(page: number): void {
    this.page.set(page);
  }

  openDetail(matchId: string): void {
    this.detail.set(null);
    this.detailLoadError.set(false);
    this.detailLoading.set(true);
    this.detailDialogRef().open();
    this.memberView.getMatchRecordDetail(this.groupId(), matchId).subscribe({
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

  /** The winning side's player names, joined — shown instead of a bare
   * "A方獲勝"/"B方獲勝": a Guest/Member reading their own group's history
   * cares who won, not which internal team letter was assigned to them. */
}
