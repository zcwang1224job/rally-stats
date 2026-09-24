import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { GroupAdminService } from '../group-admin.service';
import {
  CreateGroupRequest,
  CreateGroupResponse,
  MatchMode,
  ScoringMode,
  SchedulingMechanism,
  SportRef,
} from '../group-admin.models';
import { TurnstileWidgetComponent } from '../shared/turnstile-widget.component';
import {
  activityTimePairValidator,
  customScoringValidator,
  genericScoringValidator,
  maxMembersValidator,
  parseScoreSteps,
  schedulingMechanismMatchModeValidator,
} from '../shared/group-form-validators';
import { BADMINTON_FALLBACK, FALLBACK_CATALOG, SportsService } from '../../../core/api/sports.service';
import {
  CustomSport,
  EndMode,
  SportDefaults,
  SportsCatalogResponse,
  SportTypeKey,
} from '../../../core/api/sport.models';
import { CustomSportDialogComponent } from './custom-sport-dialog.component';
import { ConfirmDialogComponent } from '../shared/confirm-dialog.component';
import { SportSurfaceComponent } from '../../../sports/hosts/sport-surface.component';

/** Decorative only — every card also shows the activity's name. */
const SPORT_ICONS: Record<string, string> = {
  shuttle: '🏸',
  paddle: '🏓',
  pickleball: '🥒',
  tennis: '🎾',
  billiards: '🎱',
  darts: '🎯',
  board_game: '🎲',
  esports: '🎮',
  other: '🏅',
};

interface SelectedSport {
  /** A built-in sport_key, `other`, or `custom:<id>`. */
  key: string;
  typeKey: SportTypeKey;
  teamSizes: number[];
  defaults: SportDefaults;
  name: string | null;
  nameKey: string | null;
}
import { ApiError } from '../../../core/api/api-error';
import { copyTextToClipboard } from '../../../core/clipboard';
import { AuthService } from '../../auth/auth.service';
import { GroupJoinService } from '../../group-join/group-join.service';

@Component({
  selector: 'app-create-group',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    TurnstileWidgetComponent,
    SportSurfaceComponent,
    CustomSportDialogComponent,
    ConfirmDialogComponent,
  ],
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
  private readonly sports = inject(SportsService);

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
      // 043: the activity (a built-in sport_key, `other`, or `custom:<id>`)
      // and, for activities without named presets, the common parameters.
      sport: [BADMINTON_FALLBACK.sport_key],
      uses_generic_params: [false],
      other_name: ['', [Validators.maxLength(20)]],
      end_mode: ['target' as EndMode],
      target_score: [21],
      win_by: [2],
      has_cap: [true],
      cap_score: [30],
      allow_draw: [false],
      score_steps: ['1'],
    },
    {
      validators: [
        maxMembersValidator('match_mode'),
        activityTimePairValidator,
        customScoringValidator,
        schedulingMechanismMatchModeValidator('match_mode', 'scheduling_mechanism'),
        genericScoringValidator,
      ],
    },
  );

  /** 043 FR-001: the activity catalogue; the form starts on badminton. */
  readonly catalog = signal<SportsCatalogResponse>(FALLBACK_CATALOG);
  private readonly selectedKey = signal(BADMINTON_FALLBACK.sport_key);
  /** Type-specific parameters, filled by the sport type module's own
   * create-form fields (e.g. frames' "first to N frames" options). */
  readonly typeParams = this.fb.group({});

  readonly selectedSport = computed<SelectedSport>(() => {
    const key = this.selectedKey();
    const catalog = this.catalog();
    if (key.startsWith('custom:')) {
      const custom = catalog.custom.find((sport) => `custom:${sport.id}` === key);
      if (custom) {
        return { key, typeKey: custom.type_key, teamSizes: custom.team_size_options, defaults: custom.defaults, name: custom.name, nameKey: null };
      }
    }
    const builtin = catalog.builtin.find((sport) => sport.sport_key === key) ?? BADMINTON_FALLBACK;
    return {
      key: builtin.sport_key,
      typeKey: builtin.type_key,
      teamSizes: builtin.team_size_options,
      defaults: builtin.defaults,
      name: null,
      nameKey: builtin.name_key,
    };
  });

  /** Activities with named scoring presets (badminton's 21/15 points) keep
   * the preset select; every other activity edits the common parameters. */
  readonly usesPresets = computed(() => {
    const mode = this.selectedSport().defaults.scoring_mode;
    return mode === '21pt' || mode === '15pt';
  });
  readonly isOther = computed(() => this.selectedSport().key === 'other');
  readonly customSports = computed(() => this.catalog().custom);

  constructor() {
    this.loadCatalog();
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

  /** 043: picking an activity brings in its defaults (FR-009). */
  selectSport(key: string): void {
    this.selectedKey.set(key);
    this.form.controls.sport.setValue(key);
    const sport = this.selectedSport();
    const d = sport.defaults;
    const teamSize = sport.teamSizes.includes(d.team_size) ? d.team_size : sport.teamSizes[0];
    this.form.controls.match_mode.setValue(teamSize === 1 ? 'singles' : 'doubles');
    this.onMatchModeChange();
    if (this.usesPresets()) {
      this.form.controls.scoring_mode.setValue((d.scoring_mode ?? '21pt') as ScoringMode);
    } else {
      this.form.controls.scoring_mode.setValue('custom');
    }
    this.form.controls.other_name.setValidators(
      key === 'other' ? [Validators.required, Validators.maxLength(20)] : [Validators.maxLength(20)],
    );
    this.form.controls.other_name.updateValueAndValidity();
    this.form.patchValue({
      uses_generic_params: !this.usesPresets(),
      end_mode: d.end_mode,
      target_score: d.target_score,
      win_by: d.win_by,
      has_cap: d.cap_score !== null,
      cap_score: d.cap_score ?? d.target_score,
      allow_draw: d.allow_draw,
      score_steps: d.score_steps.join(','),
    });
    for (const name of Object.keys(this.typeParams.controls)) {
      this.typeParams.removeControl(name as never);
    }
  }

  isSelected(key: string): boolean {
    return this.selectedKey() === key;
  }

  /** What to call the activity: an i18n key, or a custom / "other" name. */
  sportLabel(): string {
    const sport = this.selectedSport();
    if (sport.key === 'other') {
      return this.form.controls.other_name.value.trim() || 'sports.other';
    }
    return sport.name ?? sport.nameKey ?? 'sports.other';
  }

  /** "Target score" in the activity's own unit (points, frames, …). */
  scoreNoun(): string {
    const key = this.selectedSport().key;
    const builtin = this.catalog().builtin.find((sport) => sport.sport_key === key);
    return `sports.nouns.${builtin?.nouns.score ?? 'point'}`;
  }

  iconFor(icon: string): string {
    return SPORT_ICONS[icon] ?? SPORT_ICONS['other'];
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
          ...this.sportPayload(raw),
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

  // --- 043 US4: my custom activities -----------------------------------

  readonly pendingDelete = signal<CustomSport | null>(null);
  readonly customSportErrorKey = signal<string | null>(null);
  readonly deleteSportDialog = viewChild<ConfirmDialogComponent>('deleteSportDialog');

  memberHeaders(): Record<string, string> {
    return this.memberAuthHeader() ?? {};
  }

  /** A new activity is picked straight away. */
  onCustomSportCreated(sport: CustomSport): void {
    this.customSportErrorKey.set(null);
    this.loadCatalog(true, `custom:${sport.id}`);
  }

  askDeleteCustomSport(sport: CustomSport): void {
    this.pendingDelete.set(sport);
    this.deleteSportDialog()?.open();
  }

  /** Groups already opened with it keep their name and settings. */
  confirmDeleteCustomSport(): void {
    const sport = this.pendingDelete();
    if (!sport) {
      return;
    }
    this.sports.deleteCustomSport(sport.id, this.memberHeaders()).subscribe({
      next: () => {
        this.customSportErrorKey.set(null);
        const wasSelected = this.isSelected(`custom:${sport.id}`);
        this.loadCatalog(true, wasSelected ? BADMINTON_FALLBACK.sport_key : null);
      },
      error: (error: ApiError) => this.customSportErrorKey.set(error?.i18nKey ?? 'errors.UNKNOWN_ERROR'),
    });
  }

  private loadCatalog(refresh = false, select: string | null = null): void {
    const token = this.auth.isLoggedIn() ? (this.auth.getAccessToken?.() ?? null) : null;
    this.sports
      .getCatalog(token ? { Authorization: `Bearer ${token}` } : undefined, refresh)
      .subscribe((catalog) => {
        this.catalog.set(catalog.builtin.length > 0 ? catalog : FALLBACK_CATALOG);
        if (select) {
          this.selectSport(select);
        }
      });
  }

  /** 043 contracts/sports-api.md §3: what the activity adds to the request. */
  private sportPayload(raw: ReturnType<typeof this.form.getRawValue>): Partial<CreateGroupRequest> {
    const sport = this.selectedSport();
    const teamSize = raw.match_mode === 'singles' ? 1 : 2;
    const ref: SportRef = sport.key.startsWith('custom:')
      ? { sport_key: 'custom', custom_sport_id: sport.key.slice('custom:'.length) }
      : sport.key === 'other'
        ? { sport_key: 'other', name: raw.other_name.trim() }
        : { sport_key: sport.key };
    const payload: Partial<CreateGroupRequest> = { sport: ref, team_size: teamSize };
    if (!this.usesPresets()) {
      payload.scoring_mode = 'custom';
      payload.custom_scoring = null;
      payload.end_mode = raw.end_mode;
      payload.target_score = raw.target_score;
      payload.win_by = raw.win_by;
      payload.cap_score = raw.has_cap ? raw.cap_score : null;
      payload.allow_draw = raw.end_mode === 'manual' ? raw.allow_draw : false;
      payload.score_steps = parseScoreSteps(raw.score_steps) ?? [1];
    }
    const typeParams = this.typeParams.getRawValue() as Record<string, unknown>;
    if (Object.keys(typeParams).length > 0) {
      payload.type_params = typeParams;
    }
    return payload;
  }

  private memberAuthHeader(): Record<string, string> | undefined {
    if (this.memberNickname() === null) {
      return undefined;
    }
    const token = this.auth.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : undefined;
  }
}
