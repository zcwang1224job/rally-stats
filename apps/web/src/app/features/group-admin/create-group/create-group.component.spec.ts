import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { AuthService } from '../../auth/auth.service';
import { GroupAdminService } from '../group-admin.service';
import { CreateGroupComponent } from './create-group.component';

const nicknameMember = {
  member_id: 'm1',
  email: 'a@example.com',
  nickname: '小明',
  user_number: 'U1',
  verification_status: 'verified' as const,
};

const noNicknameMember = { ...nicknameMember, nickname: null };

describe('CreateGroupComponent', () => {
  function setup(auth: Partial<AuthService>) {
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
          },
        },
        { provide: AuthService, useValue: auth },
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

  it('submitting with an empty name and no turnstile token shows the field-level error reasons', () => {
    const { fixture } = setup({ isLoggedIn: () => false });

    fixture.componentInstance.form.patchValue({ creator_nickname: '小華' });
    fixture.componentInstance.submit();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('createGroup.nameRequired');
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
