import { provideRouter, Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { ApiError } from '../../core/api/api-error';
import { MemberPublic, ResendVerificationResponse } from '../../core/api/member-auth.models';
import { AuthService } from '../auth/auth.service';
import { MemberComponent } from './member.component';

const verifiedMember: MemberPublic = {
  member_id: 'm1',
  email: 'a@example.com',
  nickname: '小明',
  user_number: 'U1',
  verification_status: 'verified',
  resend_verification_available_at: null,
};

const unverifiedMember: MemberPublic = {
  ...verifiedMember,
  verification_status: 'unverified',
};

describe('MemberComponent', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  let logoutCalls = 0;

  function setup(
    overrides: {
      member?: MemberPublic;
      resendVerification?: () => unknown;
    } = {},
  ) {
    logoutCalls = 0;
    const resendVerificationCalls: unknown[] = [];
    const resendVerification =
      overrides.resendVerification ??
      (() => {
        resendVerificationCalls.push(true);
        return of({ sent: true, available_at: '2026-01-01T00:05:00Z' } satisfies ResendVerificationResponse);
      });
    TestBed.configureTestingModule({
      imports: [MemberComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => true,
            getMe: () => of(overrides.member ?? verifiedMember),
            clearTokens: () => undefined,
            resendVerification,
            logout: () => {
              logoutCalls += 1;
            },
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(MemberComponent);
    fixture.detectChanges();
    return { fixture, resendVerificationCalls };
  }

  it('renders all 5 menu rows: match history, friends, my groups, settings, logout', () => {
    const { fixture } = setup();

    const hrefs = Array.from<HTMLAnchorElement>(
      fixture.nativeElement.querySelectorAll('.member-links a[href]'),
    ).map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/member/match-history');
    expect(hrefs).toContain('/friends');
    expect(hrefs).toContain('/member/my-groups');
    expect(hrefs).toContain('/member/settings');
    expect(fixture.nativeElement.querySelector('.logout-action')).not.toBeNull();
  });

  it('clicking logout calls AuthService.logout() and navigates home', async () => {
    const { fixture } = setup();
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigateByUrl');

    const logoutButton = fixture.nativeElement.querySelector('.logout-action') as HTMLButtonElement | null;
    logoutButton?.click();

    expect(logoutCalls).toBe(1);
    expect(navigateSpy).toHaveBeenCalledWith('/');
  });

  // 020-resend-verification-email (T013)
  it('shows the resend-verification button only for an unverified member', () => {
    const { fixture } = setup({ member: unverifiedMember });

    expect(fixture.nativeElement.querySelector('.resend-verification')).not.toBeNull();
  });

  it('does not show the resend-verification button for a verified member', () => {
    const { fixture } = setup({ member: verifiedMember });

    expect(fixture.nativeElement.querySelector('.resend-verification')).toBeNull();
  });

  it('clicking resend shows the success message on success', () => {
    const { fixture, resendVerificationCalls } = setup({ member: unverifiedMember });

    const button = fixture.nativeElement.querySelector(
      '.resend-verification button',
    ) as HTMLButtonElement;
    button.click();
    fixture.detectChanges();

    expect(resendVerificationCalls.length).toBe(1);
    expect(fixture.nativeElement.querySelector('.resend-verification__success')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.resend-verification__error')).toBeNull();
  });

  it('shows a clear "already verified" message on ALREADY_VERIFIED, without a success message', () => {
    const { fixture } = setup({
      member: unverifiedMember,
      resendVerification: () =>
        throwError(
          () =>
            ({
              errorCode: 'ALREADY_VERIFIED',
              i18nKey: 'errors.ALREADY_VERIFIED',
              detail: null,
              status: 409,
            }) satisfies ApiError,
        ),
    });

    const button = fixture.nativeElement.querySelector(
      '.resend-verification button',
    ) as HTMLButtonElement;
    button.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('errors.ALREADY_VERIFIED');
    expect(fixture.nativeElement.querySelector('.resend-verification__success')).toBeNull();
  });

  // 020-resend-verification-email (T016, US2)
  it('shows the "please wait" message on RESEND_RATE_LIMITED, without a success message', () => {
    const { fixture } = setup({
      member: unverifiedMember,
      resendVerification: () =>
        throwError(
          () =>
            ({
              errorCode: 'RESEND_RATE_LIMITED',
              i18nKey: 'errors.RESEND_RATE_LIMITED',
              detail: null,
              status: 429,
            }) satisfies ApiError,
        ),
    });

    const button = fixture.nativeElement.querySelector(
      '.resend-verification button',
    ) as HTMLButtonElement;
    button.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('errors.RESEND_RATE_LIMITED');
    expect(fixture.nativeElement.querySelector('.resend-verification__success')).toBeNull();
  });

  // 020-resend-verification-email (T020, US3)
  it('disables the button and shows the cooldown label immediately after a successful resend', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
    const { fixture } = setup({
      member: unverifiedMember,
      resendVerification: () =>
        of({ sent: true, available_at: '2026-01-01T00:05:00Z' } satisfies ResendVerificationResponse),
    });

    const button = fixture.nativeElement.querySelector(
      '.resend-verification button',
    ) as HTMLButtonElement;
    button.click();
    fixture.detectChanges();

    expect(button.disabled).toBe(true);
    expect(fixture.nativeElement.querySelector('.resend-verification__cooldown')).not.toBeNull();
  });

  it('re-enables the button automatically once the cooldown expires, without a reload', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
    const { fixture } = setup({
      member: unverifiedMember,
      resendVerification: () =>
        of({ sent: true, available_at: '2026-01-01T00:00:05Z' } satisfies ResendVerificationResponse),
    });

    const button = fixture.nativeElement.querySelector(
      '.resend-verification button',
    ) as HTMLButtonElement;
    button.click();
    fixture.detectChanges();
    expect(button.disabled).toBe(true);

    vi.advanceTimersByTime(5001);
    fixture.detectChanges();

    expect(button.disabled).toBe(false);
    expect(fixture.nativeElement.querySelector('.resend-verification__cooldown')).toBeNull();
  });

  it('starts in the cooldown state on load when resend_verification_available_at is already in the future', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
    const { fixture } = setup({
      member: { ...unverifiedMember, resend_verification_available_at: '2026-01-01T00:05:00Z' },
    });

    const button = fixture.nativeElement.querySelector(
      '.resend-verification button',
    ) as HTMLButtonElement;

    expect(button.disabled).toBe(true);
    expect(fixture.nativeElement.querySelector('.resend-verification__cooldown')).not.toBeNull();
  });
});
