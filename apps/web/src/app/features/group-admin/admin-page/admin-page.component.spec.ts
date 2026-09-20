import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import type * as Ably from 'ably';
import { Subject, of, throwError } from 'rxjs';
import { CourtManagementService } from '../court-management/court-management.service';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { AuthService } from '../../auth/auth.service';
import { FriendsService } from '../../friends/friends.service';
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
  scoreboard_scoring_enabled: false,
  detailed_scoring_enabled: false,
};

const scheduleResponse: ScheduleResponse = {
  current_round_number: 1,
  scheduling_mechanism: 'fair_rotation',
  match_mode: 'doubles',
  auto_next_round: false,
  continuous_rotation: false,
  // 'awaiting_plan' is the only phase that keeps app-round-matches-list's
  // editable auto-load off by default (editable now covers both
  // 'awaiting_start' AND 'in_progress' — see round-matches-list.component.ts)
  // so tests unrelated to the plan/start flow don't need a getRoundMatches()
  // mock; tests that DO care about that flow override round_phase explicitly.
  round_phase: 'awaiting_plan',
  courts: [],
  roster: [],
};

describe('AdminPageComponent', () => {
  function setup(
    readOnly = false,
    groupAdminOverrides: Partial<GroupAdminService> = {},
    scheduleOverrides: Partial<ScheduleService> = {},
    friendInviteOverrides: {
      selfMemberId?: string | null;
      getInviteCandidatesStatus?: FriendsService['getInviteCandidatesStatus'];
    } = {},
    realtimeSubscribe: RealtimeService['subscribe'] = () => of(),
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
          useValue: { connectionState: signal('connected'), subscribe: realtimeSubscribe },
        },
        {
          provide: CourtManagementService,
          useValue: { listCourts: () => of({ courts: [], active_court_count: 0 }) },
        },
        // 026-match-record-friend-invite: the roster-list "加好友" entry
        // needs these too — default to no member login (PIN-only session),
        // matching most existing tests' fixtures (no roster member_ids).
        {
          provide: AuthService,
          useValue: {
            getCachedMemberId: () =>
              friendInviteOverrides.selfMemberId === undefined ? null : friendInviteOverrides.selfMemberId,
          },
        },
        {
          provide: FriendsService,
          useValue: {
            getInviteCandidatesStatus:
              friendInviteOverrides.getInviteCandidatesStatus ?? (() => of({ candidates: [] })),
          },
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
    expect(buttons[0].getAttribute('aria-current')).toBe('page');
    expect(fixture.nativeElement.querySelector('.links-section')).not.toBeNull();
  });

  it('clicking 賽程 switches content away from 場地', () => {
    const fixture = setup();

    navButtons(fixture)[1].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.links-section')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('scheduleManagement.sectionTitle');
  });

  it('refetches the schedule when an idle court or the roster changes elsewhere', async () => {
    const streams = new Map<string, Subject<Ably.Message>>();
    const realtimeSubscribe = (channel: string, event: string) => {
      const key = `${channel}|${event}`;
      if (!streams.has(key)) {
        streams.set(key, new Subject<Ably.Message>());
      }
      return streams.get(key)!.asObservable();
    };
    let scheduleCalls = 0;
    setup(
      false,
      {},
      {
        getSchedule: () => {
          scheduleCalls += 1;
          return of({
            ...scheduleResponse,
            courts: [
              { court_id: 'c1', name: '1號場', current_match: null, waiting_reason: 'no_queued_match', next_up: null },
            ],
          });
        },
      },
      {},
      realtimeSubscribe as RealtimeService['subscribe'],
    );
    const initialCalls = scheduleCalls;

    // A match pulled onto the idle court, then a member joining: each burst
    // collapses into one refetch.
    streams.get('court:g1:c1|rotation.updated')!.next({} as Ably.Message);
    streams.get('court:g1:c1|match.nextRound')!.next({} as Ably.Message);
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(scheduleCalls).toBe(initialCalls + 1);

    streams.get('group:g1:notifications|member.joined')!.next({} as Ably.Message);
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(scheduleCalls).toBe(initialCalls + 2);
  });

  // 037-rest-ready-toggle T040
  it('refetches the schedule when someone rests or comes back', async () => {
    const restChanged = new Subject<Ably.Message>();
    let scheduleCalls = 0;
    setup(
      false,
      {},
      {
        getSchedule: () => {
          scheduleCalls += 1;
          return of(scheduleResponse);
        },
      },
      {},
      ((channel: string, event: string) =>
        channel === 'group:g1:notifications' && event === 'roster.restChanged'
          ? restChanged.asObservable()
          : of()) as RealtimeService['subscribe'],
    );
    const initialCalls = scheduleCalls;

    restChanged.next({} as Ably.Message);
    await new Promise((resolve) => setTimeout(resolve, 350));

    expect(scheduleCalls).toBe(initialCalls + 1);
  });

  it('marks resting players on the roster tab, with text not just colour', () => {
    const fixture = setup(false, {}, {
      getSchedule: () =>
        of({
          ...scheduleResponse,
          roster: [
            { roster_entry_id: 'r1', nickname: '小美', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: true, resting: true },
            { roster_entry_id: 'r2', nickname: '小華', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: true, resting: false },
          ],
        }),
    });

    navButtons(fixture)[2].click();
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('.roster-list li');
    expect(rows[0].textContent).toContain('scheduleManagement.restingBadge');
    expect(rows[1].textContent).not.toContain('scheduleManagement.restingBadge');
  });

  it('offers the continuous-rotation toggle for fair-rotation doubles and saves it', () => {
    const calls: boolean[] = [];
    const fixture = setup(false, {}, {
      setContinuousRotation: (_groupId: string, enabled: boolean) => {
        calls.push(enabled);
        return of({ continuous_rotation: enabled });
      },
    });

    navButtons(fixture)[1].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('scheduleManagement.continuousRotation');
    const toggle = Array.from(
      fixture.nativeElement.querySelectorAll('label.checkbox-label') as NodeListOf<HTMLLabelElement>,
    )
      .find((label) => label.textContent?.includes('scheduleManagement.continuousRotation'))!
      .querySelector('input') as HTMLInputElement;
    toggle.click();

    expect(calls).toEqual([true]);
  });

  it('hides the continuous-rotation toggle outside fair-rotation doubles', () => {
    const fixture = setup(false, {}, {
      getSchedule: () => of({ ...scheduleResponse, match_mode: 'singles' }),
    });

    navButtons(fixture)[1].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toContain('scheduleManagement.continuousRotation');
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
            serve: null,
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
    // 貼進 LINE 後要用手機預設瀏覽器開，不要落進 LINE 內建瀏覽器。
    expect(link.value).toContain('openExternalBrowser=1');
    expect(fixture.nativeElement.textContent).toContain('scheduleManagement.addGuest.shareLinkTitle');
  });

  it('the share panel offers a LINE share link alongside copy', () => {
    const fixture = setup(false, {}, {
      addGuest: () =>
        of({ roster_entry_id: 'r1', nickname: '小明', guest_session_token: 'tok-abc', created_new: true }),
    });

    navButtons(fixture)[2].click();
    fixture.detectChanges();
    fixture.componentInstance.addGuestForm.controls.nickname.setValue('小明');
    fixture.componentInstance.addGuest();
    fixture.detectChanges();

    const share = fixture.nativeElement.querySelector('.link-section a.btn--line');
    // lineit/share（而不是 line.me/R/… 那組 App scheme）——桌機點下去才不會
    // 只停在 LINE 官網。
    expect(share.getAttribute('href')).toContain('https://social-plugins.line.me/lineit/share?url=');
    // 開新分頁，才不會把 團長 正在用的管理頁面推走。
    expect(share.getAttribute('target')).toBe('_blank');
    expect(fixture.nativeElement.textContent).toContain('scheduleManagement.addGuest.shareToLine');
  });

  it('the LINE share message carries the guest\'s nickname and link', () => {
    const fixture = setup(false, {}, {
      addGuest: () =>
        of({ roster_entry_id: 'r1', nickname: '小明', guest_session_token: 'tok-abc', created_new: true }),
    });
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation(
      'zh-TW',
      { scheduleManagement: { addGuest: { lineShareMessage: '{{nickname}} 你好' } } },
      true,
    );
    translate.use('zh-TW');

    navButtons(fixture)[2].click();
    fixture.detectChanges();
    fixture.componentInstance.addGuestForm.controls.nickname.setValue('小明');
    fixture.componentInstance.addGuest();
    fixture.detectChanges();

    const share = fixture.nativeElement.querySelector('.link-section a.btn--line');
    const params = new URL(share.getAttribute('href')).searchParams;

    // 訊息帶暱稱，連結走 `url` 參數（LINE 會把它接在訊息後面送出）。
    expect(params.get('text')).toBe('小明 你好');
    expect(params.get('url')).toContain('/guest-access/tok-abc');
    // 分享出去的那條連結一樣要能跳出 LINE 內建瀏覽器。
    expect(params.get('url')).toContain('openExternalBrowser=1');
  });

  // 026-match-record-friend-invite (roster-list redesign)
  it('shows an icon-style add-friend entry on the roster list for another member, not self or a Guest', () => {
    let requestedIds: string[] = [];
    const fixture = setup(
      false,
      {},
      {
        getSchedule: () =>
          of({
            ...scheduleResponse,
            roster: [
              { roster_entry_id: 'r0', nickname: '管理員自己', status: 'active', wait_count: null, currently_playing: false, is_creator: true, is_guest: false, member_id: 'self-id' },
              { roster_entry_id: 'r1', nickname: '訪客小美', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: true },
              { roster_entry_id: 'r2', nickname: '會員小華', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: false, member_id: 'm2' },
            ],
          }),
      },
      {
        selfMemberId: 'self-id',
        getInviteCandidatesStatus: (ids: string[]) => {
          requestedIds = ids;
          return of({
            candidates: ids.map((id) => ({ member_id: id, friendship_status: 'none' as const, invite_eligible: true })),
          });
        },
      },
    );

    navButtons(fixture)[2].click();
    fixture.detectChanges();

    expect(requestedIds).toEqual(['m2']);
    const rows = fixture.nativeElement.querySelectorAll('.roster-list li');
    expect(rows[0].querySelector('app-add-friend-button')).toBeNull(); // self
    expect(rows[1].querySelector('app-add-friend-button')).toBeNull(); // guest
    expect(rows[2].querySelector('app-add-friend-button button.btn--icon')).not.toBeNull();
  });

  it('shows no add-friend entries when operating via PIN-only session (no member login)', () => {
    const fixture = setup(false, {}, {
      getSchedule: () =>
        of({
          ...scheduleResponse,
          roster: [
            { roster_entry_id: 'r2', nickname: '會員小華', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: false, member_id: 'm2' },
          ],
        }),
    });

    navButtons(fixture)[2].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('app-add-friend-button').length).toBe(0);
  });

  // 037-rest-ready-toggle US4 (T033)
  describe('rest/ready on the roster tab', () => {
    const roster = [
      { roster_entry_id: 'r0', nickname: '團長', status: 'active', wait_count: null, currently_playing: false, is_creator: true, is_guest: true },
      { roster_entry_id: 'r1', nickname: '小美', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: true, resting: true },
      { roster_entry_id: 'r2', nickname: '小華', status: 'active', wait_count: null, currently_playing: false, is_creator: false, is_guest: true },
    ];
    const restOk = {
      roster_entry_id: 'r2',
      resting: true,
      resting_since: '2026-09-19T12:00:00Z',
      currently_playing: false,
      changed: true,
    };

    function onRoster(setMemberRestState: ScheduleService['setMemberRestState']) {
      const fixture = setup(false, {}, {
        getSchedule: () => of({ ...scheduleResponse, roster }),
        setMemberRestState,
      });
      navButtons(fixture)[2].click();
      fixture.detectChanges();
      return fixture;
    }

    function rowButton(fixture: ReturnType<typeof setup>, index: number): HTMLButtonElement {
      const rows = fixture.nativeElement.querySelectorAll('.roster-list li');
      return rows[index].querySelector('app-rest-toggle-button button');
    }

    it('gives every row a button, the creator included', () => {
      const fixture = onRoster(() => of(restOk));

      expect(fixture.nativeElement.querySelectorAll('.roster-list app-rest-toggle-button').length).toBe(3);
      expect(rowButton(fixture, 1).textContent).toContain('restToggle.adminReady');
      expect(rowButton(fixture, 2).textContent).toContain('restToggle.adminRest');
    });

    it('sends the target state for that row', () => {
      const calls: [string, string, boolean, boolean | undefined][] = [];
      const fixture = onRoster((groupId, id, resting, confirm) => {
        calls.push([groupId, id, resting, confirm]);
        return of(restOk);
      });

      rowButton(fixture, 2).click();
      rowButton(fixture, 1).click();

      expect(calls).toEqual([
        ['g1', 'r2', true, false],
        ['g1', 'r1', false, false],
      ]);
    });

    it('keeps each row pending on its own', () => {
      const pending = new Subject<typeof restOk>();
      const fixture = onRoster(() => pending.asObservable());

      rowButton(fixture, 2).click();
      fixture.detectChanges();

      expect(rowButton(fixture, 2).disabled).toBe(true);
      expect(rowButton(fixture, 1).disabled).toBe(false);
    });

    it('shows a failure and leaves the row as it was', () => {
      const fixture = onRoster(() =>
        throwError(() => ({
          errorCode: 'ROSTER_ENTRY_NOT_FOUND',
          i18nKey: 'errors.ROSTER_ENTRY_NOT_FOUND',
          detail: null,
          status: 404,
        })),
      );

      rowButton(fixture, 2).click();
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('errors.ROSTER_ENTRY_NOT_FOUND');
      expect(rowButton(fixture, 2).textContent).toContain('restToggle.adminRest');
      expect(rowButton(fixture, 2).disabled).toBe(false);
    });

    it('asks first when the rest would end the round, naming the player, then resends', () => {
      const calls: [string, boolean | undefined][] = [];
      const fixture = onRoster((_g, id, _resting, confirm) => {
        calls.push([id, confirm]);
        return confirm
          ? of(restOk)
          : throwError(() => ({
              errorCode: 'REST_ENDS_ROUND',
              i18nKey: 'errors.REST_ENDS_ROUND',
              detail: { matches_to_cancel: 3 },
              status: 409,
            }));
      });

      rowButton(fixture, 2).click();
      fixture.detectChanges();

      expect(fixture.componentInstance.restEndsRoundTarget()).toEqual({
        rosterEntryId: 'r2',
        nickname: '小華',
        count: 3,
        immediate: true,
        title: 'restToggle.endsRound.title',
        body: 'restToggle.endsRound.adminBody',
      });
      expect(fixture.nativeElement.textContent).not.toContain('errors.REST_ENDS_ROUND');

      fixture.componentInstance.confirmRestEndingRound();

      expect(calls).toEqual([
        ['r2', false],
        ['r2', true],
      ]);
    });
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
