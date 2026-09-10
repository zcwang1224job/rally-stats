import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { AuthService } from '../../auth/auth.service';
import { GroupJoinService } from '../../group-join/group-join.service';
import { GroupAdminService } from '../group-admin.service';
import { CreateGroupComponent } from './create-group.component';

const nicknameMember = {
  member_id: 'm1',
  email: 'a@example.com',
  nickname: '小明',
  user_number: 'U1',
  verification_status: 'verified' as const,
  resend_verification_available_at: null,
};

const noNicknameMember = { ...nicknameMember, nickname: null };

describe('CreateGroupComponent', () => {
  function setup(auth: Partial<AuthService>, options: { activeGuestGroupId?: string | null } = {}) {
    let createGroupCall: { payload: unknown; headers: unknown } | null = null;

    TestBed.configureTestingModule({
      imports: [CreateGroupComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        {
          provide: GroupAdminService,
          useValue: {
            createGroup: (payload: unknown, headers: unknown) => {
              createGroupCall = { payload, headers };
              return of({
                group_id: 'g1',
                group_number: 1,
                admin_pin: '1234',
                admin_token: 'tok',
                current_member_count: 1,
                roster_entry_id: 'r1',
                guest_session_token: null,
              });
            },
            setAdminToken: () => undefined,
            setLastCreatedGroupId: () => undefined,
          },
        },
        { provide: AuthService, useValue: auth },
        {
          provide: GroupJoinService,
          useValue: {
            setActiveGuestGroupId: () => undefined,
            getActiveGuestGroupId: () => options.activeGuestGroupId ?? null,
            verifyActiveGuestGroupId: () => of(options.activeGuestGroupId ?? null),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(CreateGroupComponent);
    fixture.detectChanges();
    return { fixture, getCall: () => createGroupCall };
  }

  it('guest (not logged in): shows the nickname field and sends no auth header', () => {
    const { fixture, getCall } = setup({ isLoggedIn: () => false });

    expect(
      fixture.nativeElement.querySelector('input[formcontrolname="creator_nickname"]'),
    ).not.toBeNull();

    fixture.componentInstance.form.patchValue({ name: 'Test', creator_nickname: '小華' });
    fixture.componentInstance.onTurnstileVerified('tok');
    fixture.componentInstance.submit();

    const call = getCall();
    expect(call).not.toBeNull();
    expect((call!.payload as { creator_nickname: string | null }).creator_nickname).toBe('小華');
    expect(call!.headers).toBeUndefined();
  });

  it('logged-in member with a nickname: hides the nickname field, omits creator_nickname, sends Bearer header', () => {
    const { fixture, getCall } = setup({
      isLoggedIn: () => true,
      getMe: () => of(nicknameMember),
      getAccessToken: () => 'access-tok',
    });

    expect(
      fixture.nativeElement.querySelector('input[formcontrolname="creator_nickname"]'),
    ).toBeNull();
    expect(fixture.componentInstance.memberNickname()).toBe('小明');

    fixture.componentInstance.form.patchValue({ name: 'Test' });
    fixture.componentInstance.onTurnstileVerified('tok');
    fixture.componentInstance.submit();

    const call = getCall();
    expect(call).not.toBeNull();
    expect((call!.payload as { creator_nickname: string | null }).creator_nickname).toBeNull();
    expect(call!.headers).toEqual({ Authorization: 'Bearer access-tok' });
  });

  it('logged-in member with no nickname yet: redirects to /member/settings with returnTo', () => {
    const navigateCalls: unknown[][] = [];
    TestBed.configureTestingModule({
      imports: [CreateGroupComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: Router,
          useValue: {
            navigate: (...args: unknown[]) => {
              navigateCalls.push(args);
              return Promise.resolve(true);
            },
          },
        },
        {
          provide: GroupAdminService,
          useValue: { createGroup: () => of(null), setAdminToken: () => undefined },
        },
        {
          provide: AuthService,
          useValue: { isLoggedIn: () => true, getMe: () => of(noNicknameMember) },
        },
        {
          provide: GroupJoinService,
          useValue: { setActiveGuestGroupId: () => undefined, getActiveGuestGroupId: () => null },
        },
      ],
    });
    const fixture = TestBed.createComponent(CreateGroupComponent);
    fixture.detectChanges();

    expect(navigateCalls).toEqual([
      [['/member/settings'], { queryParams: { returnTo: '/groups/new' } }],
    ]);
  });

  it('logged-in member with a stale/invalid token: falls back to the guest nickname field', () => {
    const { fixture } = setup({
      isLoggedIn: () => true,
      getMe: () => throwError(() => new Error('401')),
    });

    expect(
      fixture.nativeElement.querySelector('input[formcontrolname="creator_nickname"]'),
    ).not.toBeNull();
  });

  it('singles match mode hides the doubles-only scheduling options and resets an invalid selection', () => {
    const { fixture } = setup({ isLoggedIn: () => false });

    fixture.componentInstance.form.controls.scheduling_mechanism.setValue('fixed_partner');
    fixture.componentInstance.form.controls.match_mode.setValue('singles');
    fixture.detectChanges();

    const options = Array.from<HTMLOptionElement>(
      fixture.nativeElement.querySelectorAll('select[formcontrolname="scheduling_mechanism"] option'),
    ).map((o) => o.value);
    expect(options).not.toContain('fixed_partner');
    expect(options).not.toContain('individual_mixed');

    fixture.componentInstance.onMatchModeChange();

    expect(fixture.componentInstance.form.controls.scheduling_mechanism.value).toBe('fair_rotation');
  });

  it('doubles match mode still shows the doubles-only scheduling options', () => {
    const { fixture } = setup({ isLoggedIn: () => false });

    // 021-group-creation-defaults: match_mode's initial value is now
    // 'singles' (was 'doubles') — explicitly switch to doubles here,
    // since that's what this test actually exercises.
    fixture.componentInstance.form.controls.match_mode.setValue('doubles');
    fixture.detectChanges();

    const options = Array.from<HTMLOptionElement>(
      fixture.nativeElement.querySelectorAll('select[formcontrolname="scheduling_mechanism"] option'),
    ).map((o) => o.value);
    expect(options).toContain('fixed_partner');
    expect(options).toContain('individual_mixed');
  });

  it('anonymous creation: success screen shows the un-recoverable-if-lost warning (006 FR-033)', () => {
    const { fixture } = setup({ isLoggedIn: () => false });

    fixture.componentInstance.form.patchValue({ name: 'Test', creator_nickname: '小華' });
    fixture.componentInstance.onTurnstileVerified('tok');
    fixture.componentInstance.submit();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
  });

  it('success screen shows the admin PIN in a copyable readout', () => {
    const { fixture } = setup({ isLoggedIn: () => false });

    fixture.componentInstance.form.patchValue({ name: 'Test', creator_nickname: '小華' });
    fixture.componentInstance.onTurnstileVerified('tok');
    fixture.componentInstance.submit();
    fixture.detectChanges();

    const pinInput: HTMLInputElement = fixture.nativeElement.querySelector('.pin-display');
    expect(pinInput.value).toBe('1234');
    expect(fixture.nativeElement.textContent).toContain('common.copy');
  });

  // 021-group-creation-defaults (T009, US1): blank team name no longer
  // blocks submission — the backend fills in the default, this form MUST
  // send the blank value through as-is rather than computing it itself
  // (constitution X, research.md #1).
  it('leaving name blank does not block submission — the raw (empty) value is sent as-is', () => {
    const { fixture, getCall } = setup({ isLoggedIn: () => false });

    fixture.componentInstance.form.patchValue({ creator_nickname: '小華' });
    fixture.componentInstance.onTurnstileVerified('tok');
    fixture.componentInstance.submit();
    fixture.detectChanges();

    // The form itself must accept a blank name (no client-side validation
    // error) and the request must actually go through — checked via the
    // mocked service call below, not the [role="alert"] success-screen
    // notice (which is an unrelated, expected element once submission
    // succeeds).
    const call = getCall();
    expect(call).not.toBeNull();
    expect((call!.payload as { name: string }).name).toBe('');
  });

  it('the form initial values are 單打／4人／公平輪替 (quickstart.md 情境 2, /speckit-analyze G1)', () => {
    const { fixture } = setup({ isLoggedIn: () => false });

    const controls = fixture.componentInstance.form.controls;
    expect(controls.match_mode.value).toBe('singles');
    expect(controls.max_members.value).toBe(4);
    expect(controls.scheduling_mechanism.value).toBe('fair_rotation');
  });

  it('a name over the 30-char limit shows the max-length error reason', () => {
    const { fixture } = setup({ isLoggedIn: () => false });

    fixture.componentInstance.form.patchValue({
      name: 'a'.repeat(31),
      creator_nickname: '小華',
    });
    fixture.componentInstance.onTurnstileVerified('tok');
    fixture.componentInstance.submit();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('createGroup.nameTooLong');
  });

  it('member creation: success screen does NOT show the anonymous-only warning (006 FR-033)', () => {
    const { fixture } = setup({
      isLoggedIn: () => true,
      getMe: () => of(nicknameMember),
      getAccessToken: () => 'access-tok',
    });

    fixture.componentInstance.form.patchValue({ name: 'Test' });
    fixture.componentInstance.onTurnstileVerified('tok');
    fixture.componentInstance.submit();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
  });
});

/** A Member hits ALREADY_ACTIVE_IN_ANOTHER_GROUP reactively, on submit — the
 * backend is the actual enforcement here (see group/service.py's
 * _raise_if_active_elsewhere()), unlike the Guest case above which has to be
 * checked client-side and proactively. Retrying the submit button can't ever
 * succeed either way, so this mirrors join-flow.component.spec.ts's
 * "ALREADY_ACTIVE_IN_ANOTHER_GROUP on the confirm step" describe block:
 * the button gets swapped for a way out instead of a dead-end retry loop. */
describe('CreateGroupComponent: ALREADY_ACTIVE_IN_ANOTHER_GROUP on submit', () => {
  it('replaces the submit button with a "back to list" button, and clicking it navigates to /groups', () => {
    const navigateCalls: unknown[][] = [];
    TestBed.configureTestingModule({
      imports: [CreateGroupComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: Router,
          useValue: {
            navigate: (...args: unknown[]) => {
              navigateCalls.push(args);
              return Promise.resolve(true);
            },
          },
        },
        {
          provide: GroupAdminService,
          useValue: {
            createGroup: () =>
              throwError(() => ({
                errorCode: 'ALREADY_ACTIVE_IN_ANOTHER_GROUP',
                i18nKey: 'errors.ALREADY_ACTIVE_IN_ANOTHER_GROUP',
                detail: null,
                status: 409,
              })),
            setAdminToken: () => undefined,
            setLastCreatedGroupId: () => undefined,
          },
        },
        { provide: AuthService, useValue: { isLoggedIn: () => false } },
        {
          provide: GroupJoinService,
          useValue: {
            setActiveGuestGroupId: () => undefined,
            getActiveGuestGroupId: () => null,
            verifyActiveGuestGroupId: () => of(null),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(CreateGroupComponent);
    fixture.detectChanges();

    fixture.componentInstance.form.patchValue({ name: 'Test', creator_nickname: '小華' });
    fixture.componentInstance.onTurnstileVerified('tok');
    fixture.componentInstance.submit();
    fixture.detectChanges();

    const form = fixture.nativeElement.querySelector('form');
    const buttonText = (form.querySelector('button[class="btn"]') as HTMLButtonElement)
      .textContent ?? '';
    expect(buttonText).toContain('groupJoin.backToList');
    expect(buttonText).not.toContain('createGroup.submit');
    expect(form.querySelector('button[type="submit"]')).toBeNull();

    (form.querySelector('button') as HTMLButtonElement).click();
    expect(navigateCalls).toEqual([[['/groups']]]);
  });

  it('a different submit error leaves the normal submit button in place', () => {
    TestBed.configureTestingModule({
      imports: [CreateGroupComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        {
          provide: GroupAdminService,
          useValue: {
            createGroup: () =>
              throwError(() => ({
                errorCode: 'GROUP_FULL',
                i18nKey: 'errors.GROUP_FULL',
                detail: null,
                status: 409,
              })),
            setAdminToken: () => undefined,
            setLastCreatedGroupId: () => undefined,
          },
        },
        { provide: AuthService, useValue: { isLoggedIn: () => false } },
        {
          provide: GroupJoinService,
          useValue: {
            setActiveGuestGroupId: () => undefined,
            getActiveGuestGroupId: () => null,
            verifyActiveGuestGroupId: () => of(null),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(CreateGroupComponent);
    fixture.detectChanges();

    fixture.componentInstance.form.patchValue({ name: 'Test', creator_nickname: '小華' });
    fixture.componentInstance.onTurnstileVerified('tok');
    fixture.componentInstance.submit();
    fixture.detectChanges();

    const form = fixture.nativeElement.querySelector('form');
    expect(form.querySelector('button[type="submit"]')).not.toBeNull();
    expect(form.textContent).toContain('errors.GROUP_FULL');
  });
});

/** Same-browser-only Guest nicety (research: one-active-group-per-Member
 * follow-up) — a Guest has no cross-group identity to check server-side
 * (see group/service.py _raise_if_active_elsewhere's docstring), so unlike
 * a Member (rejected server-side with ALREADY_ACTIVE_IN_ANOTHER_GROUP on
 * submit) this has to be checked client-side, and proactively — the form
 * never even renders — since there's no backend rejection to fall back on. */
describe('CreateGroupComponent: Guest already active in a different group (same browser)', () => {
  it('shows an error and a back-to-list button instead of the create form', () => {
    const navigateCalls: unknown[][] = [];
    TestBed.configureTestingModule({
      imports: [CreateGroupComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: Router,
          useValue: {
            navigate: (...args: unknown[]) => {
              navigateCalls.push(args);
              return Promise.resolve(true);
            },
          },
        },
        { provide: GroupAdminService, useValue: {} },
        { provide: AuthService, useValue: { isLoggedIn: () => false } },
        {
          provide: GroupJoinService,
          useValue: {
            getActiveGuestGroupId: () => 'some-other-group',
            verifyActiveGuestGroupId: () => of('some-other-group'),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(CreateGroupComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('form')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('errors.ALREADY_ACTIVE_IN_ANOTHER_GROUP');

    (fixture.nativeElement.querySelector('button') as HTMLButtonElement).click();
    expect(navigateCalls).toEqual([[['/groups']]]);
  });

  it('does not block a Guest with no tracked active group', () => {
    TestBed.configureTestingModule({
      imports: [CreateGroupComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        { provide: GroupAdminService, useValue: {} },
        { provide: AuthService, useValue: { isLoggedIn: () => false } },
        { provide: GroupJoinService, useValue: { getActiveGuestGroupId: () => null } },
      ],
    });
    const fixture = TestBed.createComponent(CreateGroupComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('form')).not.toBeNull();
  });

  /** Regression test: disbanding a group (manually, or via the inactivity
   * auto-disband scheduler) never touches RosterEntry.status — so a marker
   * pointing at a since-disbanded group must not permanently lock a Guest
   * out of ever creating another group. verifyActiveGuestGroupId() is
   * responsible for that liveness check; this confirms the form actually
   * un-blocks when it reports the marker as stale. */
  it('does not block a Guest whose tracked group has since disbanded (stale marker)', () => {
    TestBed.configureTestingModule({
      imports: [CreateGroupComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        { provide: GroupAdminService, useValue: {} },
        { provide: AuthService, useValue: { isLoggedIn: () => false } },
        {
          provide: GroupJoinService,
          useValue: {
            getActiveGuestGroupId: () => 'disbanded-group',
            verifyActiveGuestGroupId: () => of(null),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(CreateGroupComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('form')).not.toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('errors.ALREADY_ACTIVE_IN_ANOTHER_GROUP');
  });
});
