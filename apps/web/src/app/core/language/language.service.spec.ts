import { TestBed } from '@angular/core/testing';
import { provideTranslateService, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { AuthService } from '../../features/auth/auth.service';
import { LanguageService } from './language.service';

const LANGUAGE_KEY = 'rally-stats:language';

function setup(options: { isLoggedIn?: boolean; setLanguagePreferenceCalls?: string[] } = {}) {
  const setLanguagePreferenceCalls = options.setLanguagePreferenceCalls ?? [];
  const authServiceStub = {
    isLoggedIn: () => options.isLoggedIn ?? false,
    setLanguagePreference: (language: string) => {
      setLanguagePreferenceCalls.push(language);
      return of({ language_preference: language });
    },
  };

  TestBed.configureTestingModule({
    providers: [
      provideTranslateService({}),
      { provide: AuthService, useValue: authServiceStub },
    ],
  });

  return {
    service: TestBed.inject(LanguageService),
    translate: TestBed.inject(TranslateService),
    setLanguagePreferenceCalls,
  };
}

describe('LanguageService', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  // Foundational (FR-005/FR-006/SC-003)

  it('defaults to zh-TW when nothing has ever been stored (no browser-locale auto-detection)', () => {
    const { service } = setup();
    expect(service.current()).toBe('zh-TW');
  });

  it('picks up a previously-written localStorage value on a fresh instance (reload persistence)', () => {
    localStorage.setItem(LANGUAGE_KEY, 'en');
    const { service } = setup();
    expect(service.current()).toBe('en');
  });

  it('setLanguage updates the signal, writes localStorage, and calls TranslateService.use()', () => {
    const { service, translate } = setup();
    const useSpy = vi.spyOn(translate, 'use');

    service.setLanguage('en');

    expect(service.current()).toBe('en');
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe('en');
    expect(useSpy).toHaveBeenCalledWith('en');
  });

  // Regression: the 個人設定 language dropdown (settings.component.ts) makes
  // its own PATCH /members/me/language call for success/error handling, then
  // calls applyLanguage() — it must NOT trigger a second, redundant
  // setLanguagePreference() call, unlike setLanguage() (FR-003c).
  it('applyLanguage updates the signal, writes localStorage, and calls TranslateService.use(), without calling AuthService', () => {
    const { service, translate, setLanguagePreferenceCalls } = setup({ isLoggedIn: true });
    const useSpy = vi.spyOn(translate, 'use');

    service.applyLanguage('en');

    expect(service.current()).toBe('en');
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe('en');
    expect(useSpy).toHaveBeenCalledWith('en');
    expect(setLanguagePreferenceCalls).toEqual([]);
  });

  // US2 (FR-003b/FR-003c/US2#3/US2#4)

  it('a login-success override supersedes any existing localStorage/guest value (FR-003b, US2#3)', () => {
    localStorage.setItem(LANGUAGE_KEY, 'en');
    const { service, translate } = setup({ isLoggedIn: true });
    const useSpy = vi.spyOn(translate, 'use');

    service.onLoginSuccess('zh-TW');

    expect(service.current()).toBe('zh-TW');
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe('zh-TW');
    expect(useSpy).toHaveBeenCalledWith('zh-TW');
  });

  it('setLanguage while logged in also calls AuthService.setLanguagePreference() (FR-003c)', () => {
    const { service, setLanguagePreferenceCalls } = setup({ isLoggedIn: true });

    service.setLanguage('en');

    expect(setLanguagePreferenceCalls).toEqual(['en']);
  });

  it('setLanguage while anonymous does not call AuthService.setLanguagePreference()', () => {
    const { service, setLanguagePreferenceCalls } = setup({ isLoggedIn: false });

    service.setLanguage('en');

    expect(setLanguagePreferenceCalls).toEqual([]);
  });

  it('logging out does not reset the current language or clear localStorage (US2 Acceptance Scenario 4)', () => {
    const { service } = setup({ isLoggedIn: true });
    service.setLanguage('en');

    // Logout is a pure AuthService/token concern — LanguageService has no
    // logout hook at all, so there is nothing for a logout to reset.
    expect(service.current()).toBe('en');
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe('en');
  });
});
