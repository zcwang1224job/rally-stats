import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { CourtManagementService } from '../court-management/court-management.service';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { GroupAdminService } from '../group-admin.service';
import { AdminGroupResponse } from '../group-admin.models';
import { ScheduleService } from '../schedule-management/schedule.service';
import { ScheduleResponse } from '../schedule-management/schedule.models';
import { AdminPageComponent } from './admin-page.component';

const adminGroupResponse: AdminGroupResponse = {
  group: {
    group_id: 'g1',
    group_number: 1001,
    name: '週三團',
    has_password: false,
    current_member_count: 2,
    max_members: 4,
    match_mode: 'doubles',
    scheduling_mechanism: 'fair_rotation',
    partner_source: 'manual',
    activity_time_start: null,
    activity_time_end: null,
    status: 'active',
    created_by_member: false,
  },
  password_plaintext: null,
  read_only: false,
  base_settings_version: 1,
  admin_token_version: 1,
  join_link_token: 'join-tok',
  join_link_version: 1,
  all_courts_control_panel_token: 'all-courts-tok',
  all_courts_link_version: 1,
};

const scheduleResponse: ScheduleResponse = {
  current_round_number: 1,
  scheduling_mechanism: 'fair_rotation',
  auto_next_round: false,
  courts: [],
  roster: [],
};

describe('AdminPageComponent', () => {
  function setup(
    readOnly = false,
    groupAdminOverrides: Partial<GroupAdminService> = {},
    scheduleOverrides: Partial<ScheduleService> = {},
  ) {
    TestBed.configureTestingModule({
      imports: [AdminPageComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: convertToParamMap({ groupId: 'g1' }),
              queryParamMap: convertToParamMap({}),
            },
          },
        },
        {
          provide: GroupAdminService,
          useValue: {
            getAdminToken: () => 'admin-tok',
            getAdminView: () => of({ ...adminGroupResponse, read_only: readOnly }),
            ...groupAdminOverrides,
          },
        },
        {
          provide: ScheduleService,
          useValue: { getSchedule: () => of(scheduleResponse), ...scheduleOverrides },
        },
        {
          provide: RealtimeService,
          useValue: { connectionState: signal('connected'), subscribe: () => of() },
        },
        {
          provide: CourtManagementService,
          useValue: { listCourts: () => of({ courts: [], active_court_count: 0 }) },
        },
      ],
    });
    const fixture = TestBed.createComponent(AdminPageComponent);
    fixture.detectChanges();
    return fixture;
  }

  function navButtons(fixture: ReturnType<typeof setup>): HTMLButtonElement[] {
    return Array.from(fixture.nativeElement.querySelectorAll('.admin-nav button'));
  }

  it('shows 4 left-nav sections, defaulting to 場地 (courts)', () => {
    const fixture = setup();

    const buttons = navButtons(fixture);
    expect(buttons.length).toBe(4);
    expect(buttons[0].classList.contains('is-active')).toBe(true);
    expect(fixture.nativeElement.querySelector('.links-section')).not.toBeNull();
  });

  it('clicking 賽程 switches content away from 場地', () => {
    const fixture = setup();

    navButtons(fixture)[1].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.links-section')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('scheduleManagement.sectionTitle');
  });

  it('clicking 輪替名單 shows the roster list, not the schedule/links sections', () => {
    const fixture = setup();

    navButtons(fixture)[2].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.roster-list')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.links-section')).toBeNull();
  });

  it('clicking 設定 shows the name field alongside the password/match-mode fields', () => {
    const fixture = setup();

    navButtons(fixture)[3].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('input[formcontrolname="name"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('input[formcontrolname="password"]')).not.toBeNull();
  });

  it('the disband card gets the danger-zone visual treatment', () => {
    const fixture = setup();

    navButtons(fixture)[3].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.card--danger-zone')).not.toBeNull();
  });

  it('a freshly regenerated PIN shows a copyable readout with a copy button', () => {
    const fixture = setup();

    navButtons(fixture)[3].click();
    fixture.componentInstance.newPin.set('123456');
    fixture.detectChanges();

    const pinInput: HTMLInputElement = fixture.nativeElement.querySelector('.pin-display');
    expect(pinInput.value).toBe('123456');
    expect(fixture.nativeElement.textContent).toContain('common.copy');
  });

  it('singles match mode hides the doubles-only scheduling options and resets an invalid selection', () => {
    const fixture = setup();

    navButtons(fixture)[3].click();
    fixture.detectChanges();
    fixture.componentInstance.editForm.controls.scheduling_mechanism.setValue('individual_mixed');
    fixture.componentInstance.editForm.controls.match_mode.setValue('singles');
    fixture.detectChanges();

    const options = Array.from<HTMLOptionElement>(
      fixture.nativeElement.querySelectorAll('select[formcontrolname="scheduling_mechanism"] option'),
    ).map((o) => o.value);
    expect(options).not.toContain('fixed_partner');
    expect(options).not.toContain('individual_mixed');

    fixture.componentInstance.onMatchModeChange();

    expect(fixture.componentInstance.editForm.controls.scheduling_mechanism.value).toBe('fair_rotation');
  });

  it('read-only (disbanded) mode: all 4 nav items still render, but every section shows only the disbanded notice', () => {
    const fixture = setup(true);

    const buttons = navButtons(fixture);
    expect(buttons.length).toBe(4);

    buttons[3].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('input[formcontrolname="password"]')).toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.admin-content .status-badge').length).toBe(1);
  });

  it('hasUnfinishedMatches is false when no court has a current match', () => {
    const fixture = setup();
    fixture.componentInstance.schedule.set({
      ...scheduleResponse,
      courts: [
        { court_id: 'c1', name: '1號場', current_match: null, waiting_reason: 'no_queued_match', next_up: null },
      ],
    });

    expect(fixture.componentInstance.hasUnfinishedMatches()).toBe(false);
  });

  it('saving group settings shows a success message', () => {
    const fixture = setup(false, {
      editGroup: () => of({ ...adminGroupResponse, base_settings_version: 2 }),
    });

    navButtons(fixture)[3].click();
    fixture.detectChanges();
    fixture.componentInstance.saveGroupSettings();
    fixture.detectChanges();

    expect(fixture.componentInstance.saveSuccess()).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('adminPage.saveSuccess');
  });

  it('a failed group-settings save shows the error, not the success message', () => {
    const fixture = setup(false, {
      editGroup: () =>
        throwError(() => ({
          errorCode: 'VALIDATION_ERROR',
          i18nKey: 'errors.VALIDATION_ERROR',
          detail: null,
          status: 400,
        })),
    });

    navButtons(fixture)[3].click();
    fixture.detectChanges();
    fixture.componentInstance.saveGroupSettings();
    fixture.detectChanges();

    expect(fixture.componentInstance.saveSuccess()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain('errors.VALIDATION_ERROR');
    expect(fixture.nativeElement.textContent).not.toContain('adminPage.saveSuccess');
  });

  it('saving scoring settings shows a success message', () => {
    const fixture = setup(false, {
      editScoringSettings: () => of({ ...adminGroupResponse, base_settings_version: 2 }),
    });

    navButtons(fixture)[3].click();
    fixture.detectChanges();
    fixture.componentInstance.saveScoringSettings();
    fixture.detectChanges();

    expect(fixture.componentInstance.scoringSaveSuccess()).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('adminPage.saveSuccess');
  });

  it('hasUnfinishedMatches is true when a court still has an in-progress match', () => {
    const fixture = setup();
    fixture.componentInstance.schedule.set({
      ...scheduleResponse,
      courts: [
        {
          court_id: 'c1',
          name: '1號場',
          current_match: {
            match_id: 'm1',
            status: 'in_progress',
            participants: [],
            score_a: 0,
            score_b: 0,
          },
          waiting_reason: null,
          next_up: null,
        },
      ],
    });

    expect(fixture.componentInstance.hasUnfinishedMatches()).toBe(true);
  });

  it('adding a guest clears the nickname field and refocuses it, so 團長 can add another right away', () => {
    const fixture = setup(false, {}, {
      addGuest: () => of({ roster_entry_id: 'r1', nickname: '小明', guest_session_token: 'tok', created_new: true }),
    });

    navButtons(fixture)[2].click();
    fixture.detectChanges();
    fixture.componentInstance.addGuestForm.controls.nickname.setValue('小明');
    fixture.componentInstance.addGuest();
    fixture.detectChanges();

    expect(fixture.componentInstance.addGuestForm.controls.nickname.value).toBe('');
    expect(document.activeElement).toBe(
      fixture.componentInstance.addGuestNicknameInput().nativeElement,
    );
  });

  it.each([
    ['GROUP_FULL', 409],
    ['GROUP_DISBANDED', 409],
    ['NICKNAME_REQUIRED_FOR_GUEST', 400],
  ])('a failed add-guest (%s) shows the error, not a cleared form', (errorCode, status) => {
    const fixture = setup(false, {}, {
      addGuest: () =>
        throwError(() => ({
          errorCode,
          i18nKey: `errors.${errorCode}`,
          detail: null,
          status,
        })),
    });

    navButtons(fixture)[2].click();
    fixture.detectChanges();
    fixture.componentInstance.addGuestForm.controls.nickname.setValue('小明');
    fixture.componentInstance.addGuest();
    fixture.detectChanges();

    expect(fixture.componentInstance.addGuestErrorKey()).toBe(`errors.${errorCode}`);
    expect(fixture.nativeElement.textContent).toContain(`errors.${errorCode}`);
    expect(fixture.componentInstance.addGuestForm.controls.nickname.value).toBe('小明');
  });

  it('a 401 from add-guest triggers the same auth-failure redirect as other admin actions', () => {
    const clearAdminToken = vi.fn();
    const fixture = setup(
      false,
      {
        getAdminToken: () => 'admin-tok',
        clearAdminToken,
      },
      {
        addGuest: () =>
          throwError(() => ({
            errorCode: 'ADMIN_TOKEN_INVALID',
            i18nKey: 'errors.ADMIN_TOKEN_INVALID',
            detail: null,
            status: 401,
          })),
      },
    );

    navButtons(fixture)[2].click();
    fixture.detectChanges();
    fixture.componentInstance.addGuestForm.controls.nickname.setValue('小明');
    fixture.componentInstance.addGuest();

    expect(clearAdminToken).toHaveBeenCalledWith('g1');
  });

  it('a successful add-guest shows a share panel with that guest\'s own link', () => {
    const fixture = setup(false, {}, {
      addGuest: () =>
        of({ roster_entry_id: 'r1', nickname: '小明', guest_session_token: 'tok-abc', created_new: true }),
    });

    navButtons(fixture)[2].click();
    fixture.detectChanges();
    fixture.componentInstance.addGuestForm.controls.nickname.setValue('小明');
    fixture.componentInstance.addGuest();
    fixture.detectChanges();

    const link = fixture.nativeElement.querySelector('.link-section input[readonly]');
    expect(link.value).toContain('/guest-access/tok-abc');
    expect(fixture.nativeElement.textContent).toContain('scheduleManagement.addGuest.shareLinkTitle');
  });

  it('only shows the regenerate-link button on guest rows, not member rows', () => {
    const fixture = setup(false, {}, {
      getSchedule: () =>
        of({
          ...scheduleResponse,
          roster: [
            { roster_entry_id: 'r1', nickname: '訪客小美', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: true },
            { roster_entry_id: 'r2', nickname: '會員小華', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: false },
          ],
        }),
    });

    navButtons(fixture)[2].click();
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('.roster-list li');
    expect(rows[0].querySelector('[aria-label="scheduleManagement.regenerateGuestLinkAriaLabel"]')).not.toBeNull();
    expect(rows[1].querySelector('[aria-label="scheduleManagement.regenerateGuestLinkAriaLabel"]')).toBeNull();
  });

  it('regenerating a guest link shows a share panel with the new link', () => {
    const fixture = setup(false, {}, {
      getSchedule: () =>
        of({
          ...scheduleResponse,
          roster: [
            { roster_entry_id: 'r1', nickname: '訪客小美', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: true },
          ],
        }),
      regenerateGuestLink: () => of({ roster_entry_id: 'r1', guest_session_token: 'new-tok' }),
    });

    navButtons(fixture)[2].click();
    fixture.detectChanges();
    fixture.nativeElement
      .querySelector('[aria-label="scheduleManagement.regenerateGuestLinkAriaLabel"]')
      .click();
    fixture.detectChanges();

    const link = fixture.nativeElement.querySelector('.link-section input[readonly]');
    expect(link.value).toContain('/guest-access/new-tok');
    expect(fixture.nativeElement.textContent).toContain('訪客小美');
  });

  it('a 401 from regenerate-guest-link triggers the same auth-failure redirect as other admin actions', () => {
    const clearAdminToken = vi.fn();
    const fixture = setup(
      false,
      { getAdminToken: () => 'admin-tok', clearAdminToken },
      {
        getSchedule: () =>
          of({
            ...scheduleResponse,
            roster: [
              { roster_entry_id: 'r1', nickname: '訪客小美', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: true },
            ],
          }),
        regenerateGuestLink: () =>
          throwError(() => ({
            errorCode: 'ADMIN_TOKEN_INVALID',
            i18nKey: 'errors.ADMIN_TOKEN_INVALID',
            detail: null,
            status: 401,
          })),
      },
    );

    navButtons(fixture)[2].click();
    fixture.detectChanges();
    fixture.nativeElement
      .querySelector('[aria-label="scheduleManagement.regenerateGuestLinkAriaLabel"]')
      .click();

    expect(clearAdminToken).toHaveBeenCalledWith('g1');
  });

  it('a non-401 error from regenerate-guest-link shows the error message', () => {
    const fixture = setup(false, {}, {
      getSchedule: () =>
        of({
          ...scheduleResponse,
          roster: [
            { roster_entry_id: 'r1', nickname: '訪客小美', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: true },
          ],
        }),
      regenerateGuestLink: () =>
        throwError(() => ({
          errorCode: 'ROSTER_ENTRY_ALREADY_LEFT',
          i18nKey: 'errors.ROSTER_ENTRY_ALREADY_LEFT',
          detail: null,
          status: 409,
        })),
    });

    navButtons(fixture)[2].click();
    fixture.detectChanges();
    fixture.nativeElement
      .querySelector('[aria-label="scheduleManagement.regenerateGuestLinkAriaLabel"]')
      .click();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('errors.ROSTER_ENTRY_ALREADY_LEFT');
  });
});
