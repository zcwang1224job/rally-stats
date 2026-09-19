import { Component, DestroyRef, ElementRef, effect, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { QRCodeComponent } from 'angularx-qrcode';
import { Subject, debounceTime, interval } from 'rxjs';
import { ApiError } from '../../../core/api/api-error';
import { copyTextToClipboard } from '../../../core/clipboard';
import { InvitableFriendSummary } from '../../../core/api/group-invite.models';
import { InviteCandidateStatus } from '../../../core/api/friend.models';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { restEndsRoundCount } from '../../../core/rest-toggle-button/rest-ends-round';
import { RestToggleButtonComponent } from '../../../core/rest-toggle-button/rest-toggle-button.component';
import { waitingReasonKey } from '../../../core/waiting-reason-label';
import { AddFriendButtonComponent } from '../../../shared/add-friend-button/add-friend-button.component';
import { AuthService } from '../../auth/auth.service';
import { FriendsService } from '../../friends/friends.service';
import { GroupAdminService } from '../group-admin.service';
import {
  AdminGroupResponse,
  MatchMode,
  PartnerSource,
  SchedulingMechanism,
  ScoringMode,
} from '../group-admin.models';
import { ConfirmDialogComponent } from '../shared/confirm-dialog.component';
import {
  activityTimePairValidator,
  customScoringValidator,
  maxMembersValidator,
  schedulingMechanismMatchModeValidator,
} from '../shared/group-form-validators';
import { CourtListComponent } from '../court-management/court-list.component';
import { ScheduleService } from '../schedule-management/schedule.service';
import {
  RosterScheduleStatus,
  ScheduleResponse,
  TemporaryPairing,
} from '../schedule-management/schedule.models';
import { ManualAssignComponent } from '../schedule-management/manual-assign.component';
import { PartnershipSettingsComponent } from '../schedule-management/partnership-settings.component';
import { CourtControlComponent } from '../schedule-management/court-control.component';
import { RoundMatchesListComponent } from '../schedule-management/round-matches-list.component';

const HEARTBEAT_INTERVAL_MS = 30_000; // spec FR-035: 30s heartbeat fallback ceiling
const SCHEDULE_REFRESH_DEBOUNCE_MS = 300;

/** 010-app-wide-ui-redesign US3 (data-model.md): left-nav tab shell —
 * client-side view state only, never reflected in the URL (research.md
 * Decision 2). UI-optimization pass: the former standalone "團名"/"管理
 * 權限資訊" tabs were folded into "settings" as sub-cards (each was too
 * thin to earn its own top-level tab, and "團名" already rendered a field
 * from the same `editForm`/`saveGroupSettings()` this tab uses) — still
 * safe to split that form's DOM across sibling cards within one @switch
 * case, since Angular's FormGroup holds every control's value independent
 * of which template node currently renders it. */
type AdminSection = 'courts' | 'schedule' | 'roster' | 'invites' | 'settings';

@Component({
  selector: 'app-admin-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    ConfirmDialogComponent,
    CourtListComponent,
    QRCodeComponent,
    ManualAssignComponent,
    PartnershipSettingsComponent,
    CourtControlComponent,
    RoundMatchesListComponent,
    AddFriendButtonComponent,
    RestToggleButtonComponent,
  ],
  templateUrl: './admin-page.component.html',
  styleUrl: './admin-page.component.scss',
})
export class AdminPageComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly groupAdmin = inject(GroupAdminService);
  private readonly scheduleService = inject(ScheduleService);
  private readonly realtime = inject(RealtimeService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  private readonly friends = inject(FriendsService);

  readonly groupId = this.route.snapshot.paramMap.get('groupId')!;
  // 013-group-invite-friends: a `?section=invites` query param lets the
  // group_invite_capacity_full notification deep-link straight into the
  // invites tab — a narrow, deliberate exception to this signal otherwise
  // never being reflected in/read from the URL (it is not kept in sync on
  // further tab switches, only read once as the initial value).
  readonly activeSection = signal<AdminSection>(
    this.route.snapshot.queryParamMap.get('section') === 'invites' ? 'invites' : 'courts',
  );
  readonly invitableFriends = signal<InvitableFriendSummary[] | null>(null);
  readonly invitesErrorKey = signal<string | null>(null);
  readonly sendingInviteToMemberId = signal<string | null>(null);
  readonly adminView = signal<AdminGroupResponse | null>(null);
  readonly loading = signal(true);
  readonly errorKey = signal<string | null>(null);
  readonly saveErrorKey = signal<string | null>(null);
  readonly scoringErrorKey = signal<string | null>(null);
  readonly saveSuccess = signal(false);
  readonly scoringSaveSuccess = signal(false);
  readonly scoreboardScoringPending = signal(false);
  readonly scoreboardScoringErrorKey = signal<string | null>(null);
  readonly scoreboardScoringSaved = signal(false);
  readonly detailedScoringPending = signal(false);
  readonly detailedScoringErrorKey = signal<string | null>(null);
  readonly detailedScoringSaved = signal(false);
  readonly newPin = signal<string | null>(null);
  readonly copiedPin = signal(false);
  readonly copyPinErrorKey = signal<string | null>(null);
  readonly schedule = signal<ScheduleResponse | null>(null);
  // 026-match-record-friend-invite (roster-list redesign): batched
  // relationship + eligibility status for every roster member, re-batched
  // by the effect below whenever the roster's member id set changes. The
  // admin page can be operated via PIN-only session without a member
  // login at all (constitution IV) — when that's the case there's no
  // member_id to exclude "self" with, so the entry point simply never
  // renders (no batch call is even attempted).
  readonly inviteCandidates = signal<Map<string, InviteCandidateStatus>>(new Map());
  private lastBatchedRosterKey: string | null = null;
  readonly nextRoundErrorKey = signal<string | null>(null);
  // 018-plan-then-start UX polish: disables the 結束/規劃/開始 button while
  // its request is in flight, so a fast double-click can't fire it twice
  // (the backend's generation lock would just reject the second one with a
  // generic "try again" error — better to not let that race happen at all).
  readonly roundActionPending = signal(false);
  // 017-fixed-partner-autofill: the partnership-settings child's current
  // temporary-pairing draft (research.md #5) — held here only so
  // confirmNextRound() can pass it along; never persisted, never read back
  // from the server.
  readonly temporaryPairings = signal<TemporaryPairing[]>([]);
  readonly copiedJoinLink = signal(false);
  readonly copiedAllCourtsLink = signal(false);
  readonly copyLinkErrorKey = signal<string | null>(null);

  readonly connectionState = this.realtime.connectionState;

  readonly disbandDialog = viewChild.required<ConfirmDialogComponent>('disbandDialog');
  readonly regeneratePinDialog = viewChild.required<ConfirmDialogComponent>('regeneratePinDialog');
  readonly regenerateJoinLinkDialog =
    viewChild.required<ConfirmDialogComponent>('regenerateJoinLinkDialog');
  readonly regenerateAllCourtsLinkDialog = viewChild.required<ConfirmDialogComponent>(
    'regenerateAllCourtsLinkDialog',
  );
  readonly nextRoundDialog = viewChild.required<ConfirmDialogComponent>('nextRoundDialog');
  readonly endRoundDialog = viewChild.required<ConfirmDialogComponent>('endRoundDialog');
  readonly kickMemberDialog = viewChild.required<ConfirmDialogComponent>('kickMemberDialog');
  readonly kickMemberTarget = signal<{ rosterEntryId: string; nickname: string } | null>(null);
  readonly kickMemberErrorKey = signal<string | null>(null);

  // 037-rest-ready-toggle US4: per-row pending, so one slow request doesn't
  // lock every row; the round-ending prompt names the player it's about.
  readonly restPendingIds = signal<ReadonlySet<string>>(new Set());
  readonly restErrorKey = signal<string | null>(null);
  readonly restEndsRoundDialog = viewChild.required<ConfirmDialogComponent>('restEndsRoundDialog');
  readonly restEndsRoundTarget = signal<{
    rosterEntryId: string;
    nickname: string;
    count: number;
  } | null>(null);

  readonly addGuestNicknameInput =
    viewChild.required<ElementRef<HTMLInputElement>>('addGuestNicknameInput');
  readonly addGuestErrorKey = signal<string | null>(null);
  readonly addedGuest = signal<{ nickname: string; link: string } | null>(null);
  readonly copiedGuestLink = signal(false);
  readonly copyGuestLinkErrorKey = signal<string | null>(null);
  readonly regenerateGuestLinkErrorKey = signal<string | null>(null);

  readonly editForm = this.fb.nonNullable.group(
    {
      name: ['', [Validators.required, Validators.maxLength(30)]],
      password: [''],
      match_mode: ['doubles' as MatchMode, Validators.required],
      scheduling_mechanism: ['fair_rotation' as SchedulingMechanism, Validators.required],
      partner_source: ['manual' as PartnerSource, Validators.required],
      max_members: [4, [Validators.required, Validators.min(1)]],
      activity_time_start: [''],
      activity_time_end: [''],
    },
    {
      validators: [
        maxMembersValidator('match_mode'),
        activityTimePairValidator,
        schedulingMechanismMatchModeValidator('match_mode', 'scheduling_mechanism'),
      ],
    },
  );

  readonly scoringForm = this.fb.nonNullable.group(
    {
      scoring_mode: ['21pt' as ScoringMode, Validators.required],
      custom_target_score: [11],
      custom_deuce_threshold: [10],
      custom_cap_score: [15],
    },
    { validators: [customScoringValidator] },
  );

  readonly addGuestForm = this.fb.nonNullable.group({
    nickname: ['', [Validators.required, Validators.maxLength(20)]],
  });

  constructor() {
    const token = this.groupAdmin.getAdminToken(this.groupId);
    if (!token) {
      void this.router.navigate(['/groups/reauth']);
      return;
    }
    this.load();
    this.subscribeToDisbandEvent();
    this.subscribeToRosterEvents();
    this.scheduleRefresh
      .pipe(debounceTime(SCHEDULE_REFRESH_DEBOUNCE_MS), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadSchedule());
    interval(HEARTBEAT_INTERVAL_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());

    // 026-match-record-friend-invite: re-batch whenever the roster's set
    // of member ids changes (join/leave), not on every unrelated schedule
    // refresh (e.g. a score tick).
    effect(() => {
      const roster = this.schedule()?.roster ?? [];
      const key = roster
        .map((r) => r.member_id)
        .filter((id): id is string => !!id)
        .sort()
        .join(',');
      if (key === this.lastBatchedRosterKey) {
        return;
      }
      this.lastBatchedRosterKey = key;
      this.loadInviteCandidates(roster);
    });
  }

  private loadInviteCandidates(roster: RosterScheduleStatus[]): void {
    const selfMemberId = this.auth.getCachedMemberId();
    if (!selfMemberId) {
      this.inviteCandidates.set(new Map());
      return;
    }
    const memberIds = [
      ...new Set(
        roster
          .map((r) => r.member_id)
          .filter((id): id is string => !!id && id !== selfMemberId),
      ),
    ];
    if (memberIds.length === 0) {
      this.inviteCandidates.set(new Map());
      return;
    }
    this.friends
      .getInviteCandidatesStatus(memberIds)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.inviteCandidates.set(new Map(result.candidates.map((c) => [c.member_id, c])));
        },
        error: () => this.inviteCandidates.set(new Map()),
      });
  }

  inviteCandidateFor(memberId: string): InviteCandidateStatus | undefined {
    return this.inviteCandidates().get(memberId);
  }

  private load(): void {
    this.groupAdmin.getAdminView(this.groupId).subscribe({
      next: (view) => {
        this.adminView.set(view);
        this.loading.set(false);
        if (!view.read_only) {
          this.patchForms(view);
          this.loadSchedule();
          if (view.group.created_by_member) {
            this.loadInvitableFriends();
          }
        }
      },
      error: (error: ApiError) => this.handleAuthFailure(error),
    });
  }

  /** 場地控制區塊 (003 US1, T026) — 各場地目前比賽（或等待原因）+ 輪替名單
   * 狀態，取代 002 US4 的空骨架。實際 +1/-1、提前結束操作仍留待 007 spec
   * 串接（此區塊僅顯示狀態，不提供計分操作）。 */
  loadSchedule(): void {
    this.scheduleService.getSchedule(this.groupId).subscribe({
      next: (response) => {
        this.schedule.set(response);
        this.subscribeToCourtChannels(response);
        this.scheduleVersion.update((version) => version + 1);
      },
      error: () => this.schedule.set(null),
    });
  }

  /** 每次重新讀取賽程就加一，傳給本輪賽程清單讓它跟著更新。 */
  readonly scheduleVersion = signal(0);
  readonly waitingReasonKey = waitingReasonKey;

  // 即時事件觸發的重新讀取：同一件事常同時送出好幾個事件（例如一場打完會有
  // match.ended、rotation.updated），合併成一次讀取。
  private readonly scheduleRefresh = new Subject<void>();
  private readonly subscribedCourtChannels = new Set<string>();

  /** 以前只有「正在比賽的場地」各自的 court-control 會訂閱事件，空場地沒人
   * 聽：另一台裝置規劃並開始一輪、連續輪轉把人排上空場地、有人加入或離開
   * 時，管理頁都要等 30 秒的 heartbeat 才看得到。改成跟成員端賽程頁一樣
   * 訂閱每個場地（不含 match.scoreUpdated，比分由 court-control 自己更新，
   * 每得一分都重讀整份賽程太頻繁）。 */
  private subscribeToCourtChannels(schedule: ScheduleResponse): void {
    for (const court of schedule.courts) {
      const channel = `court:${this.groupId}:${court.court_id}`;
      if (this.subscribedCourtChannels.has(channel)) {
        continue;
      }
      this.subscribedCourtChannels.add(channel);
      for (const event of ['match.ended', 'rotation.updated', 'match.nextRound']) {
        this.realtime
          .subscribe(channel, event)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe(() => this.scheduleRefresh.next());
      }
    }
  }

  private subscribeToRosterEvents(): void {
    for (const event of ['member.joined', 'member.left', 'roster.restChanged']) {
      this.realtime
        .subscribe(`group:${this.groupId}:notifications`, event)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => this.scheduleRefresh.next());
    }
  }

  /** 013-group-invite-friends US1/US3: the "邀請好友" tab's data — only
   * ever called for a member-created group (FR-012), gated by the caller
   * above. */
  loadInvitableFriends(): void {
    this.invitesErrorKey.set(null);
    this.groupAdmin.listInvitableFriends(this.groupId).subscribe({
      next: (response) => this.invitableFriends.set(response.friends),
      error: (error: ApiError) => {
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.invitesErrorKey.set(error.i18nKey);
      },
    });
  }

  sendInvite(friend: InvitableFriendSummary): void {
    this.invitesErrorKey.set(null);
    this.sendingInviteToMemberId.set(friend.member_id);
    this.groupAdmin.sendInvite(this.groupId, friend.member_id).subscribe({
      next: () => {
        this.sendingInviteToMemberId.set(null);
        this.loadInvitableFriends();
      },
      error: (error: ApiError) => {
        this.sendingInviteToMemberId.set(null);
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.invitesErrorKey.set(error.i18nKey);
      },
    });
  }

  private patchForms(view: AdminGroupResponse): void {
    this.editForm.patchValue({
      name: view.group.name,
      password: view.password_plaintext ?? '',
      match_mode: view.group.match_mode,
      scheduling_mechanism: view.group.scheduling_mechanism,
      partner_source: view.group.partner_source,
      max_members: view.group.max_members,
      activity_time_start: view.group.activity_time_start ?? '',
      activity_time_end: view.group.activity_time_end ?? '',
    });
  }

  private subscribeToDisbandEvent(): void {
    this.realtime
      .subscribe(`group:${this.groupId}:notifications`, 'group.disbanded')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());
  }

  private handleAuthFailure(error: ApiError): void {
    this.loading.set(false);
    if (error.status === 401) {
      this.groupAdmin.clearAdminToken(this.groupId);
      void this.router.navigate(['/groups/reauth']);
      return;
    }
    this.errorKey.set(error.i18nKey);
  }

  /** 固定搭檔循環賽/個人全混搭循環賽僅適用於雙打——這兩個選項在單打模式下
   * 從下拉選單隱藏（模板），切到單打時若目前選的正是其中之一，順手重設為
   * 公平輪替，避免留下使用者看不到、卻仍卡在表單裡的無效值。 */
  onMatchModeChange(): void {
    const schedulingMechanism = this.editForm.controls.scheduling_mechanism.value;
    if (
      this.editForm.controls.match_mode.value === 'singles' &&
      (schedulingMechanism === 'fixed_partner' || schedulingMechanism === 'individual_mixed')
    ) {
      this.editForm.controls.scheduling_mechanism.setValue('fair_rotation');
    }
  }

  saveGroupSettings(): void {
    const view = this.adminView();
    if (!view || this.editForm.invalid) {
      this.editForm.markAllAsTouched();
      return;
    }
    const raw = this.editForm.getRawValue();
    this.saveErrorKey.set(null);
    this.saveSuccess.set(false);
    this.groupAdmin
      .editGroup(this.groupId, {
        expected_version: view.base_settings_version,
        name: raw.name,
        password: raw.password || undefined,
        match_mode: raw.match_mode,
        scheduling_mechanism: raw.scheduling_mechanism,
        partner_source: raw.partner_source,
        max_members: raw.max_members,
        activity_time_start: raw.activity_time_start || null,
        activity_time_end: raw.activity_time_end || null,
      })
      .subscribe({
        next: (updated) => {
          this.adminView.set(updated);
          this.patchForms(updated);
          this.loadSchedule();
          this.saveSuccess.set(true);
          setTimeout(() => this.saveSuccess.set(false), 3000);
        },
        error: (error: ApiError) => {
          if (error.status === 401) {
            this.handleAuthFailure(error);
            return;
          }
          this.saveErrorKey.set(error.i18nKey);
          if (error.errorCode === 'VERSION_CONFLICT') {
            this.load();
          }
        },
      });
  }

  saveScoringSettings(): void {
    const view = this.adminView();
    if (!view || this.scoringForm.invalid) {
      this.scoringForm.markAllAsTouched();
      return;
    }
    const raw = this.scoringForm.getRawValue();
    this.scoringErrorKey.set(null);
    this.scoringSaveSuccess.set(false);
    this.groupAdmin
      .editScoringSettings(this.groupId, {
        expected_version: view.base_settings_version,
        scoring_mode: raw.scoring_mode,
        target_score: raw.scoring_mode === 'custom' ? raw.custom_target_score : undefined,
        deuce_threshold: raw.scoring_mode === 'custom' ? raw.custom_deuce_threshold : undefined,
        cap_score: raw.scoring_mode === 'custom' ? raw.custom_cap_score : undefined,
      })
      .subscribe({
        next: (updated) => {
          this.adminView.set(updated);
          this.scoringSaveSuccess.set(true);
          setTimeout(() => this.scoringSaveSuccess.set(false), 3000);
        },
        error: (error: ApiError) => {
          if (error.status === 401) {
            this.handleAuthFailure(error);
            return;
          }
          this.scoringErrorKey.set(error.i18nKey);
          if (error.errorCode === 'VERSION_CONFLICT') {
            this.load();
          }
        },
      });
  }

  joinLinkUrl(): string {
    const view = this.adminView();
    return view ? `${window.location.origin}/join/${view.join_link_token}` : '';
  }

  allCourtsLinkUrl(): string {
    const view = this.adminView();
    return view
      ? `${window.location.origin}/control/all/${view.all_courts_control_panel_token}`
      : '';
  }

  async copyJoinLink(): Promise<void> {
    this.copyLinkErrorKey.set(null);
    if (await copyTextToClipboard(this.joinLinkUrl())) {
      this.copiedJoinLink.set(true);
      setTimeout(() => this.copiedJoinLink.set(false), 2000);
    } else {
      this.copyLinkErrorKey.set('courtManagement.copyFailed');
    }
  }

  async copyAllCourtsLink(): Promise<void> {
    this.copyLinkErrorKey.set(null);
    if (await copyTextToClipboard(this.allCourtsLinkUrl())) {
      this.copiedAllCourtsLink.set(true);
      setTimeout(() => this.copiedAllCourtsLink.set(false), 2000);
    } else {
      this.copyLinkErrorKey.set('courtManagement.copyFailed');
    }
  }

  openDisbandDialog(): void {
    this.disbandDialog().open();
  }

  confirmDisband(): void {
    this.groupAdmin.disband(this.groupId).subscribe({
      next: () => this.load(),
      error: (error: ApiError) => this.handleAuthFailure(error),
    });
  }

  openRegeneratePinDialog(): void {
    this.regeneratePinDialog().open();
  }

  confirmRegeneratePin(): void {
    this.groupAdmin.regeneratePin(this.groupId).subscribe({
      next: (response) => {
        this.groupAdmin.setAdminToken(this.groupId, response.admin_token);
        this.newPin.set(response.admin_pin);
        this.copiedPin.set(false);
        this.copyPinErrorKey.set(null);
        this.load();
      },
      error: (error: ApiError) => this.handleAuthFailure(error),
    });
  }

  async copyNewPin(): Promise<void> {
    const pin = this.newPin();
    if (!pin) {
      return;
    }
    if (await copyTextToClipboard(pin)) {
      this.copiedPin.set(true);
      setTimeout(() => this.copiedPin.set(false), 2000);
    } else {
      this.copyPinErrorKey.set('courtManagement.copyFailed');
    }
  }

  openRegenerateJoinLinkDialog(): void {
    this.regenerateJoinLinkDialog().open();
  }

  confirmRegenerateJoinLink(): void {
    const view = this.adminView();
    if (!view) {
      return;
    }
    this.groupAdmin.regenerateJoinLink(this.groupId, view.join_link_version).subscribe({
      next: () => this.load(),
      error: (error: ApiError) => this.handleAuthFailure(error),
    });
  }

  openRegenerateAllCourtsLinkDialog(): void {
    this.regenerateAllCourtsLinkDialog().open();
  }

  confirmRegenerateAllCourtsLink(): void {
    const view = this.adminView();
    if (!view) {
      return;
    }
    this.groupAdmin.regenerateAllCourtsLink(this.groupId, view.all_courts_link_version).subscribe({
      next: () => this.load(),
      error: (error: ApiError) => this.handleAuthFailure(error),
    });
  }

  /** 018-plan-then-start follow-up: 讓計分板連結也能計分——管理員在「設定」
   * 分頁開關，立即生效，不需要送出整份設定表單（跟 auto_next_round 一樣是
   * immediate toggle，只是這個設定屬於群組本體、走 group-admin API，所以
   * 更新的是 `adminView` 而不是 `schedule`）。 */
  toggleScoreboardScoring(enabled: boolean): void {
    this.scoreboardScoringErrorKey.set(null);
    this.scoreboardScoringPending.set(true);
    this.groupAdmin.setScoreboardScoring(this.groupId, enabled).subscribe({
      next: (response) => {
        this.scoreboardScoringPending.set(false);
        const view = this.adminView();
        if (view) {
          this.adminView.set({
            ...view,
            scoreboard_scoring_enabled: response.scoreboard_scoring_enabled,
          });
        }
        // 立即生效的 toggle，沒有「儲存」按鈕可以按——用跟其他設定表單一樣
        // 的「✓ 已儲存」短暫提示，讓管理員知道剛剛的點擊真的存到後端了。
        this.scoreboardScoringSaved.set(true);
        setTimeout(() => this.scoreboardScoringSaved.set(false), 3000);
      },
      error: (error: ApiError) => {
        this.scoreboardScoringPending.set(false);
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.scoreboardScoringErrorKey.set(error.i18nKey);
      },
    });
  }

  /** 031-shot-placement-scoring: same immediate-toggle pattern as
   * toggleScoreboardScoring() above. */
  toggleDetailedScoring(enabled: boolean): void {
    this.detailedScoringErrorKey.set(null);
    this.detailedScoringPending.set(true);
    this.groupAdmin.setDetailedScoring(this.groupId, enabled).subscribe({
      next: (response) => {
        this.detailedScoringPending.set(false);
        const view = this.adminView();
        if (view) {
          this.adminView.set({
            ...view,
            detailed_scoring_enabled: response.detailed_scoring_enabled,
          });
        }
        this.detailedScoringSaved.set(true);
        setTimeout(() => this.detailedScoringSaved.set(false), 3000);
      },
      error: (error: ApiError) => {
        this.detailedScoringPending.set(false);
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.detailedScoringErrorKey.set(error.i18nKey);
      },
    });
  }

  toggleAutoNextRound(enabled: boolean): void {
    this.nextRoundErrorKey.set(null);
    this.scheduleService.setAutoNextRound(this.groupId, enabled).subscribe({
      next: () => this.loadSchedule(),
      error: (error: ApiError) => {
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.nextRoundErrorKey.set(error.i18nKey);
      },
    });
  }

  toggleContinuousRotation(enabled: boolean): void {
    this.nextRoundErrorKey.set(null);
    this.scheduleService.setContinuousRotation(this.groupId, enabled).subscribe({
      next: () => this.loadSchedule(),
      error: (error: ApiError) => {
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.nextRoundErrorKey.set(error.i18nKey);
      },
    });
  }

  hasUnfinishedMatches(): boolean {
    return (this.schedule()?.courts ?? []).some((court) => court.current_match !== null);
  }

  openNextRoundDialog(): void {
    this.nextRoundDialog().open();
  }

  /** manual 模式維持原本「一鍵直接開下一輪」的行為——force-abandon 未完成
   * 的比賽並立刻產生下一輪。018-plan-then-start 之後，這是唯一還會用到
   * `nextRoundDialog`（與其 hasUnfinishedMatches() 文案判斷）的地方；其餘
   * 機制的「結束/規劃/開始」三步驟分別是各自獨立、語意單純的動作。 */
  confirmNextRound(): void {
    this.nextRoundErrorKey.set(null);
    this.roundActionPending.set(true);
    this.scheduleService.nextRound(this.groupId, this.temporaryPairings()).subscribe({
      next: (response) => {
        this.schedule.set(response);
        // A round was just generated (or force-ended) using this draft —
        // it's round-scoped only (FR-004), so it MUST NOT carry over.
        this.temporaryPairings.set([]);
        this.roundActionPending.set(false);
      },
      error: (error: ApiError) => {
        this.roundActionPending.set(false);
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.nextRoundErrorKey.set(error.i18nKey);
      },
    });
  }

  openEndRoundDialog(): void {
    this.endRoundDialog().open();
  }

  /** 018-plan-then-start: 「結束這一輪」——round_phase === 'in_progress'
   * 時顯示，是唯一會強制捨棄未完成比賽的動作，所以獨立經過確認對話框
   * （文案固定，不像 manual 的 nextRoundDialog 要視情況二選一——這顆按鈕
   * 只在真的還有未完成比賽時才會出現）。結束後 round_phase 變成
   * 'awaiting_plan'，畫面自然換成「規劃賽程安排」按鈕。 */
  confirmEndRound(): void {
    this.nextRoundErrorKey.set(null);
    this.roundActionPending.set(true);
    this.scheduleService.endRound(this.groupId).subscribe({
      next: (response) => {
        this.schedule.set(response);
        this.roundActionPending.set(false);
      },
      error: (error: ApiError) => {
        this.roundActionPending.set(false);
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.nextRoundErrorKey.set(error.i18nKey);
      },
    });
  }

  /** 018-plan-then-start: 「規劃賽程安排」——round_phase === 'awaiting_plan'
   * 時顯示。本輪這時已經沒有任何未完成的比賽（要嘛自然打完，要嘛剛被
   * confirmEndRound() 結束），所以這一步不會捨棄任何東西，不需要確認
   * 對話框，點下去就直接送出。成功後 round_phase 變成 'awaiting_start'，
   * 讓管理員接著用 `app-round-matches-list` 檢視/調整（交換場次、拖曳排
   * 序），再按下方出現的「比賽開始」。 */
  confirmPlanRound(): void {
    this.nextRoundErrorKey.set(null);
    this.roundActionPending.set(true);
    this.scheduleService.planRound(this.groupId, this.temporaryPairings()).subscribe({
      next: (response) => {
        this.schedule.set(response);
        this.temporaryPairings.set([]);
        this.roundActionPending.set(false);
      },
      error: (error: ApiError) => {
        this.roundActionPending.set(false);
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.nextRoundErrorKey.set(error.i18nKey);
      },
    });
  }

  /** 018-plan-then-start: 「比賽開始」——round_phase === 'awaiting_start'
   * 時顯示，確認已規劃好的賽程並派上場地開打。這一步同樣不會強制結束任何
   * 比賽（規劃階段就已經處理過），不經過確認對話框。 */
  confirmStartRound(): void {
    this.nextRoundErrorKey.set(null);
    this.roundActionPending.set(true);
    this.scheduleService.startRound(this.groupId).subscribe({
      next: (response) => {
        this.schedule.set(response);
        this.roundActionPending.set(false);
      },
      error: (error: ApiError) => {
        this.roundActionPending.set(false);
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.nextRoundErrorKey.set(error.i18nKey);
      },
    });
  }

  onTemporaryPairingsChange(pairings: TemporaryPairing[]): void {
    this.temporaryPairings.set(pairings);
  }

  openKickMemberDialog(rosterEntryId: string, nickname: string): void {
    this.kickMemberTarget.set({ rosterEntryId, nickname });
    this.kickMemberErrorKey.set(null);
    this.kickMemberDialog().open();
  }

  confirmKickMember(): void {
    const target = this.kickMemberTarget();
    if (!target) {
      return;
    }
    this.scheduleService.kickMember(this.groupId, target.rosterEntryId).subscribe({
      next: () => this.loadSchedule(),
      error: (error: ApiError) => {
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.kickMemberErrorKey.set(error.i18nKey);
      },
    });
  }

  /** 037-rest-ready-toggle US4: put a player on rest or back. No
   * confirmation — except a rest the backend refuses with REST_ENDS_ROUND
   * (it would end the round on the spot), which asks first, naming them. */
  setMemberRest(
    rosterEntryId: string,
    nickname: string,
    resting: boolean,
    confirmRoundEnd = false,
  ): void {
    if (this.restPendingIds().has(rosterEntryId)) {
      return;
    }
    this.restErrorKey.set(null);
    this.restPendingIds.update((ids) => new Set(ids).add(rosterEntryId));
    const done = () =>
      this.restPendingIds.update((ids) => {
        const next = new Set(ids);
        next.delete(rosterEntryId);
        return next;
      });
    this.scheduleService
      .setMemberRestState(this.groupId, rosterEntryId, resting, confirmRoundEnd)
      .subscribe({
        next: () => {
          done();
          this.loadSchedule();
        },
        error: (error: ApiError) => {
          done();
          if (error.status === 401) {
            this.handleAuthFailure(error);
            return;
          }
          const count = restEndsRoundCount(error);
          if (count !== null && !confirmRoundEnd) {
            this.restEndsRoundTarget.set({ rosterEntryId, nickname, count });
            this.restEndsRoundDialog().open();
            return;
          }
          this.restErrorKey.set(error.i18nKey);
        },
      });
  }

  confirmRestEndingRound(): void {
    const target = this.restEndsRoundTarget();
    if (target) {
      this.setMemberRest(target.rosterEntryId, target.nickname, true, true);
    }
  }

  addGuest(): void {
    if (this.addGuestForm.invalid) {
      this.addGuestForm.markAllAsTouched();
      return;
    }
    this.addGuestErrorKey.set(null);
    const nickname = this.addGuestForm.getRawValue().nickname;
    this.scheduleService.addGuest(this.groupId, nickname).subscribe({
      next: (response) => {
        this.addedGuest.set({
          nickname: response.nickname,
          link: `${window.location.origin}/guest-access/${response.guest_session_token}`,
        });
        this.copiedGuestLink.set(false);
        this.copyGuestLinkErrorKey.set(null);
        this.addGuestForm.reset({ nickname: '' });
        // FR-009: keep focus in the field so 團長 can add several guests in
        // a row without re-clicking into it each time.
        this.addGuestNicknameInput().nativeElement.focus();
        this.loadSchedule();
      },
      error: (error: ApiError) => {
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.addGuestErrorKey.set(error.i18nKey);
      },
    });
  }

  regenerateGuestLink(member: RosterScheduleStatus): void {
    this.regenerateGuestLinkErrorKey.set(null);
    this.scheduleService.regenerateGuestLink(this.groupId, member.roster_entry_id).subscribe({
      next: (response) => {
        // Reuses the same share panel/signal as a fresh add-guest — the
        // resulting UI (link + QR + copy) is identical either way.
        this.addedGuest.set({
          nickname: member.nickname,
          link: `${window.location.origin}/guest-access/${response.guest_session_token}`,
        });
        this.copiedGuestLink.set(false);
        this.copyGuestLinkErrorKey.set(null);
      },
      error: (error: ApiError) => {
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.regenerateGuestLinkErrorKey.set(error.i18nKey);
      },
    });
  }

  async copyAddedGuestLink(): Promise<void> {
    const guest = this.addedGuest();
    if (!guest) {
      return;
    }
    if (await copyTextToClipboard(guest.link)) {
      this.copiedGuestLink.set(true);
      setTimeout(() => this.copiedGuestLink.set(false), 2000);
    } else {
      this.copyGuestLinkErrorKey.set('courtManagement.copyFailed');
    }
  }
}
