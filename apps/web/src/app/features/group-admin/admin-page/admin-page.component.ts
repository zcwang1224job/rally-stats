import { Component, DestroyRef, ElementRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { QRCodeComponent } from 'angularx-qrcode';
import { interval } from 'rxjs';
import { ApiError } from '../../../core/api/api-error';
import { copyTextToClipboard } from '../../../core/clipboard';
import { InvitableFriendSummary } from '../../../core/api/group-invite.models';
import { RealtimeService } from '../../../core/realtime/ably.service';
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
import { ScheduleResponse } from '../schedule-management/schedule.models';
import { ManualAssignComponent } from '../schedule-management/manual-assign.component';
import { PartnershipSettingsComponent } from '../schedule-management/partnership-settings.component';
import { CourtControlComponent } from '../schedule-management/court-control.component';
import { RoundMatchesListComponent } from '../schedule-management/round-matches-list.component';

const HEARTBEAT_INTERVAL_MS = 30_000; // spec FR-035: 30s heartbeat fallback ceiling

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
  readonly newPin = signal<string | null>(null);
  readonly copiedPin = signal(false);
  readonly copyPinErrorKey = signal<string | null>(null);
  readonly schedule = signal<ScheduleResponse | null>(null);
  readonly nextRoundErrorKey = signal<string | null>(null);
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
  readonly kickMemberDialog = viewChild.required<ConfirmDialogComponent>('kickMemberDialog');
  readonly kickMemberTarget = signal<{ rosterEntryId: string; nickname: string } | null>(null);
  readonly kickMemberErrorKey = signal<string | null>(null);

  readonly addGuestNicknameInput =
    viewChild.required<ElementRef<HTMLInputElement>>('addGuestNicknameInput');
  readonly addGuestErrorKey = signal<string | null>(null);
  readonly addedGuest = signal<{ nickname: string; link: string } | null>(null);
  readonly copiedGuestLink = signal(false);
  readonly copyGuestLinkErrorKey = signal<string | null>(null);

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
    interval(HEARTBEAT_INTERVAL_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());
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
      next: (response) => this.schedule.set(response),
      error: () => this.schedule.set(null),
    });
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

  hasUnfinishedMatches(): boolean {
    return (this.schedule()?.courts ?? []).some((court) => court.current_match !== null);
  }

  openNextRoundDialog(): void {
    this.nextRoundDialog().open();
  }

  confirmNextRound(): void {
    this.nextRoundErrorKey.set(null);
    this.scheduleService.nextRound(this.groupId).subscribe({
      next: (response) => this.schedule.set(response),
      error: (error: ApiError) => {
        if (error.status === 401) {
          this.handleAuthFailure(error);
          return;
        }
        this.nextRoundErrorKey.set(error.i18nKey);
      },
    });
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
