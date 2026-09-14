# Phase 0 Research: 新增英文語系

## 1. How does an anonymous/no-login screen learn which languages are supported?

**Decision**: Make `GET /members/me/supported-languages` auth-free (drop the
`require_member` dependency) instead of adding a second, parallel endpoint.
Keep the same path/handler/response shape (`SupportedLanguagesResponse {
languages: string[] }`).

**Rationale**: The endpoint's content (`SUPPORTED_LANGUAGES = ("zh-TW",
"en")`) is static, non-member-specific config — it was only gated by
`require_member` in 022 because at the time its only caller was the
authenticated 個人設定 page. FR-003/FR-003a now require the same list to be
readable by anonymous visitors (global nav-shell switcher) and by the 3
nav-shell-less court/scoreboard/control-panel routes, none of which carry a
Bearer token. Relaxing one existing endpoint is simpler than introducing a
second `GET /supported-languages` that would immediately duplicate it —
there is exactly one such list in the system. The `/members/me/...` path
segment becomes slightly stale-sounding but is not worth a breaking rename
since it's an internal API only consumed by this codebase's own frontend.

**Alternatives considered**:
- New top-level `GET /supported-languages`, auth-free, keep the old one for
  the settings page: rejected — two endpoints returning identical content
  is pure duplication with no behavioral benefit; the old one has exactly
  one caller (`settings.component.ts`), which is safe to repoint at the
  now-public version of the same handler.
- Hardcode `['zh-TW', 'en']` in the frontend instead of fetching it: rejected
  — breaks the existing single-source-of-truth design from 022
  (`SUPPORTED_LANGUAGES` in `schemas.py`) that this feature explicitly reuses
  per spec Assumptions ("延續既有...不需要資料庫層級的變更").

## 2. Where does the "current language" state live, and what resolves it on load?

**Decision**: A new `LanguageService` (`providedIn: 'root'`), constructed
once at app init, computes the starting language with this precedence:
1. Logged-in member with a valid session → `member.language_preference`
   (already present on the `GET /members/me` / login response, no extra
   call needed).
2. Otherwise → `localStorage['rally-stats.language']` if set and supported.
3. Otherwise → `'zh-TW'` (existing hardcoded default; FR-005 forbids
   browser-locale auto-detection).

It then calls `TranslateService.use(lang)` once resolved. `setLanguage(lang)`
updates the signal + localStorage immediately, calls `.use(lang)`, and —
only when a member is currently logged in — also calls the existing
`AuthService.setLanguagePreference(lang)` (022) so FR-003c's two-way sync
holds. On a successful login response, `LanguageService` re-resolves from
the fresh `member.language_preference`, overriding whatever localStorage/
guest value was active (FR-003b — account wins, no flicker per US2#3: the
override happens synchronously in the same login-success handler, before
the member-area view renders).

**Rationale**: Centralizing this in one injectable avoids duplicating
localStorage/precedence logic across the 4 places a switcher appears.
Reusing the login response's already-included `language_preference` avoids
an extra round-trip. This mirrors the existing pattern in `AuthService`
where session state is a private signal exposed read-only.

**Alternatives considered**:
- Let each `LanguageSwitcherComponent` instance manage its own localStorage
  read: rejected — 4 independent copies of precedence logic is exactly the
  duplication Constitution VI (Modularity) warns against, and risks the 4
  instances disagreeing after a login.
- Store the anonymous choice in a cookie instead of localStorage: rejected —
  no existing use of cookies for client-only UI state in this codebase, and
  localStorage is simpler for a same-browser, non-network-visible pattern.

## 3. Why does `ngx-translate` currently never call `.use()`, and is that safe to introduce?

Confirmed via exhaustive `grep -rln "TranslateService"` that no code path
calls `.use()` today — `app.config.ts` hardcodes `lang`/`fallbackLang` to
`'zh-TW'` and nothing ever switches at runtime. Introducing the first
`.use()` call is new but low-risk: `ngx-translate`'s `HttpLoader` already
lazy-fetches `/assets/i18n/{lang}.json?v=timestamp` on demand, which is
exactly the mechanism `.use('en')` will trigger the first time a viewer
picks English. `fallbackLang` stays `'zh-TW'` so any key temporarily missing
from a freshly-added `en.json` degrades to the existing Chinese text rather
than an empty string — this bounds risk on any FR-001 translation gap.

## 4. How should the two transactional emails localize (FR-010)?

**Decision**: Add a small module-level mapping in `member/service.py`
(near `_verification_link`/`_reset_link`) keyed by language code, each value
a `(subject, body_template)` pair, e.g.:

```python
_VERIFICATION_EMAIL = {
    "zh-TW": ("請驗證你的信箱", "請點擊以下連結完成信箱驗證：{link}"),
    "en": ("Verify your email", "Please click the following link to verify your email: {link}"),
}
```

`_issue_verification_token_and_email()` and `forgot_password()` look up
`_VERIFICATION_EMAIL.get(member.language_preference, _VERIFICATION_EMAIL["zh-TW"])`
(defaulting unknown/legacy values to zh-TW, never raising) before calling
`send_email()`. `resend_verification()` reuses
`_issue_verification_token_and_email()` unchanged and inherits the fix for
free.

**Rationale**: Matches the existing code shape (already two small private
link-builder functions in the same file) with minimal structural change.
Keeps the localization decision entirely server-side and keyed off the
already-authoritative `member.language_preference` column — no dependency
on the request's client-side language state, which the backend never sees
for these background-triggered sends anyway (e.g. `forgot_password` doesn't
have a "current UI language" to read from other than the stored member row).

**Alternatives considered**:
- Route email subject/body through the frontend's `en.json`/`zh-TW.json`
  translation files somehow: rejected — those are frontend HTTP-loader
  assets; the backend has no built-in i18n framework and pulling one in for
  2 short templates would violate Constitution IX (avoid unnecessary new
  dependencies) for no real benefit.

## 5. How does a brand-new registration seed `language_preference` (FR-009)?

**Decision**: `RegisterRequest` (backend `schemas.py`, frontend
`member-auth.models.ts`) gains an optional `language: str | None` field.
`register.component.ts`'s `submit()` populates it from
`this.translate.currentLang()` (already injected there today for the
`turnstileLanguage` getter — no new injection needed). Backend `register()`
validates the incoming value against `SUPPORTED_LANGUAGES`; if present and
valid, passes it to the new `Member(...)` constructor call in place of
relying on the column default; if absent or invalid, falls back to the
existing column default (`'zh-TW'`) — a malformed/unexpected value must
never block account creation.

**Rationale**: The registering browser already knows its current language
(from `LanguageService`/`TranslateService`, resolved per research item #2)
before the register form is even submitted — passing it through is a single
optional field, no new endpoint.

**Alternatives considered**:
- Have the frontend call `PATCH /members/me/language` immediately after
  register succeeds: rejected — that endpoint requires
  `require_verified_member` (a brand-new unverified account would be
  rejected), and it's an avoidable extra round-trip for something knowable
  at registration time.

## 6. FR-008 bug fix scope

Confirmed in `settings.component.html`: the existing 022 dropdown's `@for
(language of languages())` loop renders `{{ 'member.settings.basic.
languageZhTW' | translate }}` for every option regardless of which `language`
value is being iterated — a latent bug (every option shows "繁體中文" today,
harmless only because `SUPPORTED_LANGUAGES` currently has exactly one
entry). Fix: a frontend-only cosmetic display-name map (e.g. `{'zh-TW':
'繁體中文'/'Traditional Chinese', 'en': 'English'}`, itself pulled from the
i18n table so it also flips language with the rest of the UI) keyed by the
actual `language` value in each iteration, applied both in this existing
dropdown and in the new `LanguageSwitcherComponent`. This map is a cosmetic
label only — `SUPPORTED_LANGUAGES` (backend) remains the sole source of
truth for *which* languages exist.
