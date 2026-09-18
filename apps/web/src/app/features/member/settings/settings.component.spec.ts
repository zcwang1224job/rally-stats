import { Component } from '@angular/core';
import { convertToParamMap, ActivatedRoute, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { ApiError } from '../../../core/api/api-error';
import {
  LoginRecordsResponse,
  MemberPublic,
  PrivacySettingsResponse,
} from '../../../core/api/member-auth.models';
import { AuthService } from '../../auth/auth.service';
import { LanguageService } from '../../../core/language/language.service';
import { SettingsComponent } from './settings.component';

@Component({ selector: 'app-stub-member', template: '' })
class StubMemberComponent {}

const member: MemberPublic = {
  member_id: 'm1',
  email: 'a@example.com',
  nickname: '小明',
  user_number: 'U1',
  verification_status: 'verified',
  resend_verification_available_at: null,
  language_preference: 'zh-TW',
  allow_search: true,
  share_match_records_with_friends: true,
  allow_friend_invite_from_match_pages: true,
  linked_oauth_providers: [],
  has_password: true,
};

const emptyLoginRecords: LoginRecordsResponse = { records: [], page: 1, total_pages: 1 };

function setup(
  overrides: {
    member?: MemberPublic;
    loginRecords?: LoginRecordsResponse;
    setLanguagePreference?: () => unknown;
    setPrivacySettings?: () => unknown;
    setNickname?: () => unknown;
    changePassword?: () => unknown;
    deleteAccount?: () => unknown;
    startOAuthFlow?: () => unknown;
    unlinkOauthIdentity?: () => unknown;
    addEmail?: () => unknown;
    queryParams?: Record<string, string>;
  } = {},
) {
  const calls = { setPrivacySettings: 0, logout: 0 };
  const deleteAccountCalls: unknown[] = [];
  const privacyPayloads: unknown[] = [];
  const startOAuthFlowCalls: unknown[] = [];
  const unlinkOauthIdentityCalls: unknown[] = [];
  const addEmailCalls: unknown[] = [];
  const authServiceStub = {
    getMe: () => of(overrides.member ?? member),
    getSupportedLanguages: () => of({ languages: ['zh-TW', 'en'] }),
    setLanguagePreference:
      overrides.setLanguagePreference ??
      (() => of({ ...(overrides.member ?? member), language_preference: 'zh-TW' })),
    getLoginRecords: () => of(overrides.loginRecords ?? emptyLoginRecords),
    setNickname: overrides.setNickname ?? (() => of(overrides.member ?? member)),
    changePassword:
      overrides.changePassword ?? (() => of({ changed: true, access_token: 'a', refresh_token: 'r' })),
    setPrivacySettings: (payload: unknown) => {
      calls.setPrivacySettings += 1;
      privacyPayloads.push(payload);
      return overrides.setPrivacySettings
        ? overrides.setPrivacySettings()
        : of({
            allow_search: true,
            share_match_records_with_friends: true,
            allow_friend_invite_from_match_pages: true,
          } satisfies PrivacySettingsResponse);
    },
    deleteAccount: (currentPassword: string) => {
      deleteAccountCalls.push(currentPassword);
      return overrides.deleteAccount ? overrides.deleteAccount() : of({ deleted: true });
    },
    logout: () => {
      calls.logout += 1;
    },
    startOAuthFlow: (...args: unknown[]) => {
      startOAuthFlowCalls.push(args);
      return overrides.startOAuthFlow
        ? overrides.startOAuthFlow()
        : of({ authorize_url: 'https://accounts.google.com/o/oauth2/v2/auth?x=1' });
    },
    unlinkOauthIdentity: (...args: unknown[]) => {
      unlinkOauthIdentityCalls.push(args);
      return overrides.unlinkOauthIdentity ? overrides.unlinkOauthIdentity() : of(undefined);
    },
    addEmail: (...args: unknown[]) => {
      addEmailCalls.push(args);
      return overrides.addEmail
        ? overrides.addEmail()
        : of({ verification_email_sent: true });
    },
  };

  TestBed.configureTestingModule({
    imports: [SettingsComponent],
    providers: [
      provideRouter([
        { path: '', component: StubMemberComponent },
        { path: 'member', component: StubMemberComponent },
      ]),
      provideTranslateService({}),
      { provide: AuthService, useValue: authServiceStub },
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { queryParamMap: convertToParamMap(overrides.queryParams ?? {}) } },
      },
    ],
  });
  const fixture = TestBed.createComponent(SettingsComponent);
  fixture.detectChanges();
  return {
    fixture,
    calls,
    deleteAccountCalls,
    privacyPayloads,
    startOAuthFlowCalls,
    unlinkOauthIdentityCalls,
    addEmailCalls,
  };
}

type Section = 'basic' | 'accountDetails' | 'security' | 'privacy';

function switchTo(fixture: ReturnType<typeof setup>['fixture'], section: Section): void {
  const tab = fixture.nativeElement.querySelector(
    `.settings-tab[data-section="${section}"]`,
  ) as HTMLButtonElement;
  tab.click();
  fixture.detectChanges();
}

describe('SettingsComponent', () => {
  it('renders exactly the four section tabs: basic/accountDetails/security/privacy', () => {
    const { fixture } = setup();

    const sections = Array.from<HTMLButtonElement>(
      fixture.nativeElement.querySelectorAll('.settings-tab'),
    ).map((el) => el.getAttribute('data-section'));
    expect(sections).toEqual(['basic', 'accountDetails', 'security', 'privacy']);
  });

  it('the 基本設定 tab starts active by default', () => {
    const { fixture } = setup();

    const basicTab = fixture.nativeElement.querySelector('.settings-tab[data-section="basic"]');
    expect(basicTab.classList.contains('settings-tab--active')).toBe(true);
    expect(fixture.nativeElement.querySelector('input[formControlName="nickname"]')).not.toBeNull();
  });

  it('pre-fills the nickname field with the member\'s current nickname on load', () => {
    const { fixture } = setup();

    const input = fixture.nativeElement.querySelector(
      'input[formControlName="nickname"]',
    ) as HTMLInputElement;
    expect(input.value).toBe('小明');
  });

  // Foundational regression: existing nickname behavior unchanged under the new layout.
  it('submitting a valid nickname shows the success badge', () => {
    const { fixture } = setup();

    const input = fixture.nativeElement.querySelector(
      'input[formControlName="nickname"]',
    ) as HTMLInputElement;
    input.value = '新暱稱';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const nicknameForm = fixture.nativeElement.querySelectorAll('form')[0] as HTMLFormElement;
    nicknameForm.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('.status-badge--success').length).toBe(1);
  });

  // Foundational regression: existing password behavior unchanged under the new 安全性 section.
  it('submitting a valid password change in the 安全性 section shows the success badge', () => {
    const { fixture } = setup();
    switchTo(fixture, 'security');

    const [current, next, confirm] = Array.from<HTMLInputElement>(
      fixture.nativeElement.querySelectorAll('input[type="password"]'),
    );
    current.value = 'abc12345';
    current.dispatchEvent(new Event('input'));
    next.value = 'newpass123';
    next.dispatchEvent(new Event('input'));
    confirm.value = 'newpass123';
    confirm.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('.status-badge--success').length).toBe(1);
  });

  // 025-delete-account: danger-zone delete-account form.
  it('submitting the delete-account form with the wrong password shows the error inline and does not log out', () => {
    const { fixture, calls } = setup({
      deleteAccount: () =>
        throwError(
          () =>
            ({
              errorCode: 'CURRENT_PASSWORD_INCORRECT',
              i18nKey: 'errors.CURRENT_PASSWORD_INCORRECT',
              detail: null,
              status: 400,
            }) satisfies ApiError,
        ),
    });
    switchTo(fixture, 'security');

    const deleteAccountForm = fixture.nativeElement.querySelectorAll('form')[1] as HTMLFormElement;
    const passwordInput = deleteAccountForm.querySelector(
      'input[type="password"]',
    ) as HTMLInputElement;
    passwordInput.value = 'wrong-password';
    passwordInput.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    deleteAccountForm.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('errors.CURRENT_PASSWORD_INCORRECT');
    expect(calls.logout).toBe(0);
  });

  it('submitting the delete-account form with the correct password logs out and navigates away', () => {
    const { fixture, calls, deleteAccountCalls } = setup();
    switchTo(fixture, 'security');

    const deleteAccountForm = fixture.nativeElement.querySelectorAll('form')[1] as HTMLFormElement;
    const passwordInput = deleteAccountForm.querySelector(
      'input[type="password"]',
    ) as HTMLInputElement;
    passwordInput.value = 'abc12345';
    passwordInput.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    deleteAccountForm.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(deleteAccountCalls).toEqual(['abc12345']);
    expect(calls.logout).toBe(1);
  });

  // US1: language preference dropdown.
  it('shows one option per supported language, pre-selected to the member\'s current preference', () => {
    const { fixture } = setup();

    const options = Array.from<HTMLOptionElement>(
      fixture.nativeElement.querySelectorAll('select option'),
    );
    expect(options.length).toBe(2);
    expect(options[0].value).toBe('zh-TW');
    expect(options[1].value).toBe('en');
    const select = fixture.nativeElement.querySelector('select') as HTMLSelectElement;
    expect(select.value).toBe('zh-TW');
  });

  it('024-add-english-language FR-008: each option shows its own display-name key, not the same one repeated', () => {
    const { fixture } = setup();

    const options = Array.from<HTMLOptionElement>(
      fixture.nativeElement.querySelectorAll('select option'),
    );
    // No real translations are loaded under provideTranslateService({}), so
    // `| translate` echoes the raw key — this is how this repo's tests
    // verify each option is keyed by ITS OWN language code, not a single
    // hardcoded key repeated for every iteration (the pre-fix bug).
    expect(options[0].textContent).toContain('languageNames.zh-TW');
    expect(options[1].textContent).toContain('languageNames.en');
    expect(options[0].textContent).not.toBe(options[1].textContent);
  });

  it('submitting the language form shows the success badge', () => {
    const { fixture } = setup();

    const languageForm = fixture.nativeElement.querySelectorAll('form')[1] as HTMLFormElement;
    languageForm.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('.status-badge--success').length).toBe(1);
  });

  // 024-add-english-language FR-003c: saving here must take effect
  // immediately, the same as the global switcher — not just persist
  // server-side and wait for a reload.
  it('submitting the language form applies the new language immediately via LanguageService', () => {
    const { fixture } = setup({
      setLanguagePreference: () =>
        of({ ...member, language_preference: 'en' } satisfies MemberPublic),
    });
    const languageService = TestBed.inject(LanguageService);
    const applySpy = vi.spyOn(languageService, 'applyLanguage');

    const languageForm = fixture.nativeElement.querySelectorAll('form')[1] as HTMLFormElement;
    languageForm.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(applySpy).toHaveBeenCalledWith('en');
    expect(languageService.current()).toBe('en');
  });

  it('shows the error i18n key when the language update fails', () => {
    const { fixture } = setup({
      setLanguagePreference: () =>
        throwError(
          () =>
            ({
              errorCode: 'LANGUAGE_NOT_SUPPORTED',
              i18nKey: 'errors.LANGUAGE_NOT_SUPPORTED',
              detail: null,
              status: 400,
            }) satisfies ApiError,
        ),
    });

    const languageForm = fixture.nativeElement.querySelectorAll('form')[1] as HTMLFormElement;
    languageForm.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('errors.LANGUAGE_NOT_SUPPORTED');
  });

  // US2: login records.
  it('shows the empty state when there are no login records', () => {
    const { fixture } = setup({ loginRecords: emptyLoginRecords });
    switchTo(fixture, 'accountDetails');

    expect(fixture.nativeElement.querySelector('.empty-state')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.login-records')).toBeNull();
  });

  it('renders login records newest-first with a yyyy/MM/dd HH:mm:ss timestamp, and supports pagination', () => {
    const { fixture } = setup({
      loginRecords: {
        records: [
          { created_at: '2026-09-13T10:00:00Z', device_category: 'mobile' },
          { created_at: '2026-09-12T08:00:00Z', device_category: 'desktop' },
        ],
        page: 1,
        total_pages: 3,
      },
    });
    switchTo(fixture, 'accountDetails');

    const items = fixture.nativeElement.querySelectorAll('.login-records li');
    expect(items.length).toBe(2);
    const timestampPattern = /^\d{4}\/\d{2}\/\d{2} \d{2}:\d{2}:\d{2}$/;
    expect(items[0].querySelector('.login-records__time')?.textContent?.trim()).toMatch(
      timestampPattern,
    );
    expect(items[1].querySelector('.login-records__time')?.textContent?.trim()).toMatch(
      timestampPattern,
    );

    const buttons = Array.from<HTMLButtonElement>(
      fixture.nativeElement.querySelectorAll('.pagination button'),
    );
    const prevButton = buttons[0];
    const nextButton = buttons[buttons.length - 1];
    expect(prevButton.disabled).toBe(true);
    expect(nextButton.disabled).toBe(false);
  });

  // US4: privacy — checkbox is only a draft; saving requires clicking 儲存.
  it('reflects the current allow_search value on the checkbox but does not save until the form is submitted', () => {
    const { fixture, calls } = setup();
    switchTo(fixture, 'privacy');

    const [allowSearchCheckbox] = Array.from<HTMLInputElement>(
      fixture.nativeElement.querySelectorAll('input[type="checkbox"]'),
    );
    expect(allowSearchCheckbox.checked).toBe(true);

    allowSearchCheckbox.checked = false;
    allowSearchCheckbox.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    expect(calls.setPrivacySettings).toBe(0);
    expect(fixture.nativeElement.querySelectorAll('.status-badge--success').length).toBe(0);

    const form = fixture.nativeElement.querySelector('.card form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(calls.setPrivacySettings).toBe(1);
    expect(fixture.nativeElement.querySelectorAll('.status-badge--success').length).toBe(1);
  });

  // 026-match-record-friend-invite (US3, T043)
  it('renders the new toggle at its current value and persists a change via PATCH', () => {
    const { fixture, privacyPayloads } = setup({
      member: { ...member, allow_friend_invite_from_match_pages: true },
    });
    switchTo(fixture, 'privacy');

    const checkboxes = Array.from<HTMLInputElement>(
      fixture.nativeElement.querySelectorAll('input[type="checkbox"]'),
    );
    const inviteToggle = checkboxes[2];
    expect(inviteToggle.checked).toBe(true);

    inviteToggle.checked = false;
    inviteToggle.dispatchEvent(new Event('change'));
    const form = fixture.nativeElement.querySelector('.card form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(privacyPayloads).toEqual([
      {
        allow_search: true,
        share_match_records_with_friends: true,
        allow_friend_invite_from_match_pages: false,
      },
    ]);
  });

  it('shows a non-color on/off text label next to each privacy toggle (constitution VII), on the same row as its description', () => {
    const { fixture } = setup();
    switchTo(fixture, 'privacy');

    const rows = fixture.nativeElement.querySelectorAll('.toggle-row');
    expect(rows.length).toBe(3);
    for (const row of Array.from(rows)) {
      const el = row as HTMLElement;
      // description text and the toggle control MUST be in the same row.
      expect(el.querySelector('.toggle-row__label')).not.toBeNull();
      expect(el.querySelector('.toggle-switch input[type="checkbox"]')).not.toBeNull();
      expect(el.querySelector('.toggle-switch__state')?.textContent?.trim().length).toBeGreaterThan(0);
    }
  });

  it('shows the error i18n key when a privacy update fails', () => {
    const { fixture } = setup({
      setPrivacySettings: () =>
        throwError(
          () =>
            ({
              errorCode: 'EMAIL_NOT_VERIFIED',
              i18nKey: 'errors.EMAIL_NOT_VERIFIED',
              detail: null,
              status: 403,
            }) satisfies ApiError,
        ),
    });
    switchTo(fixture, 'privacy');

    const form = fixture.nativeElement.querySelector('.card form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('errors.EMAIL_NOT_VERIFIED');
  });

  // Polish (FR-026): cross-section state isolation.
  it('does not lose an unsaved nickname draft when switching to another section and saving it', () => {
    const { fixture } = setup();

    const input = fixture.nativeElement.querySelector(
      'input[formControlName="nickname"]',
    ) as HTMLInputElement;
    input.value = '草稿暱稱';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    switchTo(fixture, 'security');
    const [current, next, confirm] = Array.from<HTMLInputElement>(
      fixture.nativeElement.querySelectorAll('input[type="password"]'),
    );
    current.value = 'abc12345';
    current.dispatchEvent(new Event('input'));
    next.value = 'newpass123';
    next.dispatchEvent(new Event('input'));
    confirm.value = 'newpass123';
    confirm.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    switchTo(fixture, 'basic');
    const nicknameInputAgain = fixture.nativeElement.querySelector(
      'input[formControlName="nickname"]',
    ) as HTMLInputElement;
    expect(nicknameInputAgain.value).toBe('草稿暱稱');
  });

  // 027-google-line-oauth-login US3 (T037)
  describe('OAuth account linking', () => {
    it('shows "已綁定" for a linked provider and a "綁定" button for an unlinked one', () => {
      const { fixture } = setup({ member: { ...member, linked_oauth_providers: ['google'] } });
      switchTo(fixture, 'security');

      const rows = fixture.nativeElement.querySelectorAll('.oauth-link-row');
      expect(rows.length).toBe(2);
      expect(rows[0].querySelector('.status-badge--success')).not.toBeNull();
      expect(rows[1].querySelector('.status-badge--success')).toBeNull();
      expect(rows[1].querySelector('button')?.textContent).toContain(
        'member.settings.oauth.link',
      );
    });

    it('clicking 綁定 calls startOAuthFlow(provider, "link") and navigates to the authorize_url', () => {
      const { fixture, startOAuthFlowCalls } = setup();
      switchTo(fixture, 'security');
      const navigateSpy = vi.spyOn(
        fixture.componentInstance as unknown as { navigateToAuthorizeUrl: (url: string) => void },
        'navigateToAuthorizeUrl',
      );

      fixture.componentInstance.linkOauth('google');

      expect(startOAuthFlowCalls).toEqual([['google', 'link']]);
      expect(navigateSpy).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/v2/auth?x=1');
    });

    it('clicking 解除綁定 calls unlinkOauthIdentity and removes the provider from the badge state', () => {
      const { fixture, unlinkOauthIdentityCalls } = setup({
        member: { ...member, linked_oauth_providers: ['google'] },
      });
      switchTo(fixture, 'security');

      fixture.componentInstance.unlinkOauth('google');
      fixture.detectChanges();

      expect(unlinkOauthIdentityCalls).toEqual([['google']]);
      expect(fixture.componentInstance.isOauthLinked('google')).toBe(false);
    });

    it('shows an inline error when unlinking is refused as the last login method', () => {
      const { fixture } = setup({
        member: { ...member, linked_oauth_providers: ['google'] },
        unlinkOauthIdentity: () =>
          throwError(
            () =>
              ({
                errorCode: 'LAST_LOGIN_METHOD',
                i18nKey: 'errors.LAST_LOGIN_METHOD',
                detail: null,
                status: 409,
              }) satisfies ApiError,
          ),
      });
      switchTo(fixture, 'security');

      fixture.componentInstance.unlinkOauth('google');
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('errors.LAST_LOGIN_METHOD');
    });

    it('shows the FR-013 reminder only when the member has neither a password nor an email', () => {
      const { fixture } = setup({
        member: { ...member, has_password: false, email: null },
      });
      switchTo(fixture, 'security');

      expect(fixture.nativeElement.querySelector('.account-recovery-reminder')).not.toBeNull();
    });

    it('does not show the FR-013 reminder for a member with a password', () => {
      const { fixture } = setup({ member: { ...member, has_password: true, email: null } });
      switchTo(fixture, 'security');

      expect(fixture.nativeElement.querySelector('.account-recovery-reminder')).toBeNull();
    });

    it('hides the "目前密碼" field on both forms when the member has no password yet', () => {
      const { fixture } = setup({ member: { ...member, has_password: false } });
      switchTo(fixture, 'security');

      const passwordInputs = fixture.nativeElement.querySelectorAll('input[type="password"]');
      // Only new_password + confirm_new_password remain (current_password hidden
      // on both the password form and the delete-account form).
      expect(passwordInputs.length).toBe(2);
    });

    it('renders the add-email form only when the member has no email yet, and submitting it calls addEmail', () => {
      const { fixture, addEmailCalls } = setup({ member: { ...member, email: null } });
      switchTo(fixture, 'security');

      const emailInput = fixture.nativeElement.querySelector(
        'input[formControlName="email"]',
      ) as HTMLInputElement;
      expect(emailInput).not.toBeNull();
      emailInput.value = 'new@example.com';
      emailInput.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      const addEmailForm = emailInput.closest('form') as HTMLFormElement;
      addEmailForm.dispatchEvent(new Event('submit'));
      fixture.detectChanges();

      expect(addEmailCalls).toEqual([['new@example.com']]);
      expect(fixture.nativeElement.textContent).toContain('member.settings.oauth.addEmailSent');
    });

    it('does not render the add-email form for a member who already has an email', () => {
      const { fixture } = setup();
      switchTo(fixture, 'security');

      expect(fixture.nativeElement.querySelector('input[formControlName="email"]')).toBeNull();
    });

    it('reads a successful oauth_link redirect result, shows the message, and refreshes the member', () => {
      const { fixture } = setup({
        queryParams: { oauth_link: 'success', provider: 'google' },
        member: { ...member, linked_oauth_providers: ['google'] },
      });
      switchTo(fixture, 'security');

      expect(fixture.nativeElement.textContent).toContain('member.settings.oauth.linkSuccess');
    });

    it('reads an error oauth_link redirect result and shows the mapped error key', () => {
      const { fixture } = setup({
        queryParams: { oauth_link: 'error', code: 'OAUTH_PROVIDER_ALREADY_LINKED' },
      });
      switchTo(fixture, 'security');

      expect(fixture.nativeElement.textContent).toContain('errors.OAUTH_PROVIDER_ALREADY_LINKED');
    });
  });
});
