import { Component, computed, inject, signal } from '@angular/core';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { GroupAdminService } from '../group-admin.service';
import { CreateGroupResponse, MatchMode, ScoringMode, SchedulingMechanism } from '../group-admin.models';
import { TurnstileWidgetComponent } from '../shared/turnstile-widget.component';
import {
  activityTimePairValidator,
  customScoringValidator,
  maxMembersValidator,
  schedulingMechanismMatchModeValidator,
} from '../shared/group-form-validators';
import { ApiError } from '../../../core/api/api-error';
import { copyTextToClipboard } from '../../../core/clipboard';
import { AuthService } from '../../auth/auth.service';
import { GroupJoinService } from '../../group-join/group-join.service';

@Component({
  selector: 'app-create-group',
  imports: [ReactiveFormsModule, TranslatePipe, TurnstileWidgetComponent],
  templateUrl: './create-group.component.html',
  styleUrl: './create-group.component.scss',
})
export class CreateGroupComponent {
  private readonly fb = inject(FormBuilder);
  private readonly groupAdmin = inject(GroupAdminService);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);
  private readonly auth = inject(AuthService);
  private readonly groupJoin = inject(GroupJoinService);

  readonly submitting = signal(false);
  readonly errorKey = signal<string | null>(null);
  readonly result = signal<CreateGroupResponse | null>(null);
  readonly turnstileToken = signal<string | null>(null);
  readonly copiedPin = signal(false);
  readonly copyPinErrorKey = signal<string | null>(null);
  /** Set once a logged-in Member's own nickname is confirmed (constructor).
   * When non-null, the form hides its own nickname field and the submitted
   * group links back to this Member identity instead of creating a Guest
   * roster entry — see group-admin.service.ts `createGroup()`. */
  readonly memberNickname = signal<string | null>(null);
  // Same-browser-only Guest nicety (no cross-group identity exists to
  // check server-side — see group-join.service.ts's
  // setActiveGuestGroupId() docstring): a Guest already tracked as active
  // in some group can't be blocked from creating a second one server-side
  // the way a Member is (ALREADY_ACTIVE_IN_ANOTHER_GROUP), so this is
  // checked here proactively instead — the form never even renders.
  // `checkingGuestGroup` covers the brief window where the marker is being
  // verified against the live group (it may be stale — e.g. that group
  // disbanded since — see verifyActiveGuestGroupId()'s docstring) so the
  // form doesn't flash visible before flipping to blocked.
  readonly blockedByActiveGuestGroup = signal(false);
  readonly checkingGuestGroup = signal(false);

  // A Member hits this same error reactively, on submit (the backend is
  // the actual enforcement for a Member — see the block above for why a
  // Guest needs the proactive version instead). Retrying the submit button
  // can't ever succeed here either — same reasoning as join-flow.component
  // .ts's confirm step — so it gets the same swap-for-a-way-out treatment
  // instead of a dead-end retry loop.
  readonly alreadyActiveElsewhere = computed(
    () => this.errorKey() === 'errors.ALREADY_ACTIVE_IN_ANOTHER_GROUP',
  );

  readonly form = this.fb.nonNullable.group(
    {
      // 021-group-creation-defaults FR-001: no longer required — left
      // blank, the backend fills in "{建立者暱稱}的羽球團" (research.md
      // #1); this form MUST NOT compute that default itself (constitution X).
      name: ['', [Validators.maxLength(30)]],
      password: [''],
      max_members: [4, [Validators.required, Validators.min(1)]],
      // FR-002: 單打 is now the form's initial match mode (was 雙打).
      match_mode: ['singles' as MatchMode, Validators.required],
      scheduling_mechanism: ['fair_rotation' as SchedulingMechanism, Validators.required],
      scoring_mode: ['21pt' as ScoringMode, Validators.required],
      custom_target_score: [11],
      custom_deuce_threshold: [10],
      custom_cap_score: [15],
      activity_time_start: [''],
      activity_time_end: [''],
      creator_nickname: ['', [Validators.required, Validators.maxLength(20)]],
    },
    {
      validators: [
        maxMembersValidator('match_mode'),
        activityTimePairValidator,
        customScoringValidator,
        schedulingMechanismMatchModeValidator('match_mode', 'scheduling_mechanism'),
      ],
    },
  );

  constructor() {
    if (!this.auth.isLoggedIn()) {
      if (this.groupJoin.getActiveGuestGroupId() !== null) {
        this.checkingGuestGroup.set(true);
        this.groupJoin.verifyActiveGuestGroupId().subscribe((stillActiveGroupId) => {
          this.checkingGuestGroup.set(false);
          this.blockedByActiveGuestGroup.set(stillActiveGroupId !== null);
        });
      }
      return;
    }
    this.auth.getMe().subscribe({
      next: (member) => {
        if (member.nickname === null) {
          void this.router.navigate(['/member/settings'], {
            queryParams: { returnTo: '/groups/new' },
          });
          return;
        }
        this.memberNickname.set(member.nickname);
        this.form.controls.creator_nickname.clearValidators();
        this.form.controls.creator_nickname.updateValueAndValidity();
      },
      // Same as join-flow.component.ts: a stale/invalid access token falls
      // back to the anonymous/Guest creation path rather than blocking it.
      error: () => undefined,
    });
  }

  /** 固定搭檔循環賽/個人全混搭循環賽僅適用於雙打（見
   * group-form-validators.ts 的 schedulingMechanismMatchModeValidator）——
   * 這兩個選項在單打模式下從下拉選單隱藏（模板），所以切到單打時若目前
   * 選的正是其中之一，順手重設為公平輪替，避免留下使用者看不到、卻仍
   * 卡在表單裡的無效值。 */
  onMatchModeChange(): void {
    const schedulingMechanism = this.form.controls.scheduling_mechanism.value;
    if (
      this.form.controls.match_mode.value === 'singles' &&
      (schedulingMechanism === 'fixed_partner' || schedulingMechanism === 'individual_mixed')
    ) {
      this.form.controls.scheduling_mechanism.setValue('fair_rotation');
    }
  }

  onTurnstileVerified(token: string): void {
    this.turnstileToken.set(token);
  }

  onTurnstileExpired(): void {
    this.turnstileToken.set(null);
  }

  submit(): void {
    if (this.form.invalid || !this.turnstileToken()) {
      this.form.markAllAsTouched();
      return;
    }

    const raw = this.form.getRawValue();
    this.submitting.set(true);
    this.errorKey.set(null);

    this.groupAdmin
      .createGroup(
        {
          name: raw.name,
          password: raw.password || null,
          max_members: raw.max_members,
          match_mode: raw.match_mode,
          scheduling_mechanism: raw.scheduling_mechanism,
          scoring_mode: raw.scoring_mode,
          custom_scoring:
            raw.scoring_mode === 'custom'
              ? {
                  target_score: raw.custom_target_score,
                  deuce_threshold: raw.custom_deuce_threshold,
                  cap_score: raw.custom_cap_score,
                }
              : null,
          activity_time_start: raw.activity_time_start || null,
          activity_time_end: raw.activity_time_end || null,
          creator_nickname: this.memberNickname() === null ? raw.creator_nickname : null,
          turnstile_token: this.turnstileToken()!,
        },
        this.memberAuthHeader(),
      )
      .subscribe({
        next: (response) => {
          this.submitting.set(false);
          this.groupAdmin.setAdminToken(response.group_id, response.admin_token);
          if (this.memberNickname() === null) {
            this.groupAdmin.setLastCreatedGroupId(response.group_id);
            this.groupJoin.setActiveGuestGroupId(response.group_id);
            if (response.guest_session_token) {
              this.groupJoin.setGuestSessionToken(response.group_id, response.guest_session_token);
            }
          }
          this.result.set(response);
        },
        error: (error: ApiError) => {
          this.submitting.set(false);
          this.errorKey.set(error.i18nKey);
        },
      });
  }

  async copyAdminPin(): Promise<void> {
    const pin = this.result()?.admin_pin;
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

  goToAdmin(): void {
    const groupId = this.result()?.group_id;
    if (groupId) {
      void this.router.navigate(['/groups', groupId, 'admin']);
    }
  }

  goToGroupList(): void {
    void this.router.navigate(['/groups']);
  }

  get turnstileLanguage(): string {
    return this.translate.currentLang() === 'zh-TW' ? 'zh-tw' : 'auto';
  }

  private memberAuthHeader(): Record<string, string> | undefined {
    if (this.memberNickname() === null) {
      return undefined;
    }
    const token = this.auth.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : undefined;
  }
}
