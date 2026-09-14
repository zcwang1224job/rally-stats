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
  } = {},
) {
  const calls = { setPrivacySettings: 0 };
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
      void payload;
      return overrides.setPrivacySettings
        ? overrides.setPrivacySettings()
        : of({
            allow_search: true,
            share_match_records_with_friends: true,
          } satisfies PrivacySettingsResponse);
    },
  };

  TestBed.configureTestingModule({
    imports: [SettingsComponent],
    providers: [
      provideRouter([{ path: 'member', component: StubMemberComponent }]),
      provideTranslateService({}),
      { provide: AuthService, useValue: authServiceStub },
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { queryParamMap: convertToParamMap({}) } },
      },
    ],
  });
  const fixture = TestBed.createComponent(SettingsComponent);
  fixture.detectChanges();
  return { fixture, calls };
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

    const [prevButton, nextButton] = Array.from<HTMLButtonElement>(
      fixture.nativeElement.querySelectorAll('.pagination button'),
    );
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

  it('shows a non-color on/off text label next to each privacy toggle (constitution VII), on the same row as its description', () => {
    const { fixture } = setup();
    switchTo(fixture, 'privacy');

    const rows = fixture.nativeElement.querySelectorAll('.toggle-row');
    expect(rows.length).toBe(2);
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
});
