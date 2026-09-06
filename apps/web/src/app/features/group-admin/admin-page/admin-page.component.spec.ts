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
  ) {
    TestBed.configureTestingModule({
      imports: [AdminPageComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ groupId: 'g1' }) } },
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
          useValue: { getSchedule: () => of(scheduleResponse) },
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

  it('shows 6 left-nav sections, defaulting to 場地 (courts)', () => {
    const fixture = setup();

    const buttons = navButtons(fixture);
    expect(buttons.length).toBe(6);
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

  it('clicking 團名 shows the name-only form', () => {
    const fixture = setup();

    navButtons(fixture)[3].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('input[formcontrolname="name"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('input[formcontrolname="password"]')).toBeNull();
  });

  it('clicking 管理員設定 shows the settings form with the password/match-mode fields', () => {
    const fixture = setup();

    navButtons(fixture)[5].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('input[formcontrolname="password"]')).not.toBeNull();
  });

  it('singles match mode hides the doubles-only scheduling options and resets an invalid selection', () => {
    const fixture = setup();

    navButtons(fixture)[5].click();
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

  it('read-only (disbanded) mode: all 6 nav items still render, but every section shows only the disbanded notice', () => {
    const fixture = setup(true);

    const buttons = navButtons(fixture);
    expect(buttons.length).toBe(6);

    buttons[5].click();
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

    navButtons(fixture)[5].click();
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

    navButtons(fixture)[5].click();
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

    navButtons(fixture)[5].click();
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
});
