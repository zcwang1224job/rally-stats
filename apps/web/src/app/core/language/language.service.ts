import { Injectable, inject, signal } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';
import { AuthService } from '../../features/auth/auth.service';

const LANGUAGE_STORAGE_KEY = 'rally-stats:language';
const DEFAULT_LANGUAGE = 'zh-TW';

/** 024-add-english-language FR-005/FR-006: the app's starting display
 * language, read synchronously (no Angular DI needed) so it can seed
 * `provideTranslateService({ lang: ... })` in app.config.ts before the
 * injector exists. Never inspects `navigator.language` — an existing user
 * who has never touched a switcher MUST keep seeing `zh-TW` (SC-004). */
export function resolveInitialLanguage(): string {
  return localStorage.getItem(LANGUAGE_STORAGE_KEY) ?? DEFAULT_LANGUAGE;
}

/** research.md #2: single source of truth for "what language is the app
 * currently showing", for both the global switcher (FR-003) and the three
 * standalone nav-shell-less switchers (FR-003a). One localStorage key does
 * double duty as both "the anonymous guest's browser-local choice" and
 * "the last language a login resolved to" (FR-003b) — `onLoginSuccess()`
 * always overwrites it, so a subsequent reload/logout keeps showing
 * whichever value most recently won, without needing a second key. */
@Injectable({ providedIn: 'root' })
export class LanguageService {
  private readonly translate = inject(TranslateService);
  private readonly auth = inject(AuthService);

  private readonly currentSignal = signal(
    this.translate.currentLang() || resolveInitialLanguage(),
  );
  readonly current = this.currentSignal.asReadonly();

  /** Updates only the local display language — signal, localStorage, and
   * `TranslateService.use()`. Never touches the backend itself; callers
   * that already made their own `PATCH /members/me/language` call (the
   * existing 個人設定 dropdown, which needs its own success/error handling)
   * call this afterwards so the two entry points converge on one value
   * without a redundant second API call (FR-003c). */
  applyLanguage(language: string): void {
    this.currentSignal.set(language);
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    this.translate.use(language);
  }

  /** FR-002/FR-003c: called by any switcher (global or standalone). While a
   * member session is active, also syncs to the existing 個人設定
   * `language_preference` setting (022) — the two are meant to be the same
   * value, never two independently-drifting ones. */
  setLanguage(language: string): void {
    this.applyLanguage(language);
    if (this.auth.isLoggedIn()) {
      this.auth.setLanguagePreference(language).subscribe();
    }
  }

  /** FR-003b/US2#3: called right after a successful login with the member's
   * stored `language_preference` — always wins over whatever anonymous
   * guest choice (or a previous member's leftover) was active, with no
   * flicker (this runs synchronously in the login success handler, before
   * the member-area view renders). */
  onLoginSuccess(memberLanguage: string): void {
    this.applyLanguage(memberLanguage);
  }
}
