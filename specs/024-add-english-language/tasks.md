---
description: "Task list for 024-add-english-language"
---

# Tasks: 新增英文語系

**Input**: Design documents from `/specs/024-add-english-language/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/language-api.md, quickstart.md

**Tests**: Included — Constitution II (Test-First for Core Domain Logic) applies, and this session's established convention is tests alongside/before each implementation task, run to full-suite green before a task is considered done.

**Organization**: Tasks are grouped by user story (US1 = P1, US2 = P2) per spec.md priorities.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 or US2
- Paths are exact, relative to repo root

---

## Phase 1: Setup

**Purpose**: Unblock everything else — extend the one existing source of truth for which languages exist.

- [X] T001 Extend `SUPPORTED_LANGUAGES = ("zh-TW",)` to `("zh-TW", "en")` in `apps/api/app/domains/member/schemas.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure both user stories depend on — the public supported-languages endpoint, the `LanguageService`, and the reusable switcher component. No visible English text yet (that's US1).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Contract test: `GET /members/me/supported-languages` succeeds with no `Authorization` header and returns `{"languages": ["zh-TW", "en"]}` in `apps/api/tests/contract/test_member_personal_settings.py`
- [X] T003 Remove the `Depends(security.require_member)` dependency from `GET /members/me/supported-languages` in `apps/api/app/domains/member/router.py` (depends on T002; contracts/language-api.md)
- [X] T004 [P] `LanguageService` unit tests in `apps/web/src/app/core/language/language.service.spec.ts`: resolves starting language as member preference > localStorage > `'zh-TW'` default (no browser-locale auto-detection, FR-005); a fresh service instance (simulating a reload) picks up a previously-written localStorage value (FR-006/SC-003 — this is the canonical test for reload persistence; Phase 4 does not repeat it); `setLanguage()` updates the signal, writes localStorage, and calls `TranslateService.use()`
- [X] T005 Implement `LanguageService` (`providedIn: 'root'`) in `apps/web/src/app/core/language/language.service.ts` covering the precedence + `setLanguage()` behavior from T004 (depends on T004; research.md #2)
- [X] T006 [P] `LanguageSwitcherComponent` unit tests in `apps/web/src/app/core/language/language-switcher.component.spec.ts`: renders one option per language from `AuthService.getSupportedLanguages()` with that language's own display name (FR-008 — never the same label repeated), calls `LanguageService.setLanguage()` on selection
- [X] T007 [P] Implement `LanguageSwitcherComponent` in `apps/web/src/app/core/language/language-switcher.component.ts` + `.html` + `.scss`, with a frontend-only display-name map keyed by language code (depends on T006, T005; research.md #6)
- [X] T008 Resolve the app's starting language via `LanguageService` at init (replacing the hardcoded `lang: 'zh-TW'` literal's role as the *only* source) in `apps/web/src/app/app.config.ts` (depends on T005)

**Checkpoint**: Public endpoint, `LanguageService`, and `LanguageSwitcherComponent` exist and are tested. Nothing user-visible changes yet (no `en.json`, no switcher embedded anywhere).

---

## Phase 3: User Story 1 - 切換為英文並看到完整英文介面 (Priority: P1) 🎯 MVP

**Goal**: A user can switch to English (via a switcher visible everywhere, including the 3 nav-shell-less routes) and see the entire existing app — screens, backend error messages, and transactional emails — in English.

**Independent Test**: Switch language to English; browse ≥5 distinct screens (home, login, create-group, scoreboard, member settings) with no residual Traditional Chinese; trigger a backend validation error and confirm it renders in English; open a scoreboard/control-panel link with no login and confirm a switcher is present even while loading/invalid.

### Tests for User Story 1

- [X] T009 [P] [US1] Update `apps/web/src/app/features/member/settings/settings.component.spec.ts`: the language dropdown shows each option's own display name (fix for the existing `languageZhTW`-hardcoded-every-iteration bug), not one repeated label
- [X] T010 [P] [US1] Backend unit tests for language-aware transactional emails in new file `apps/api/tests/unit/domains/member/test_email_language.py`: `forgot_password()` and `_issue_verification_token_and_email()` send the English subject/body when `member.language_preference == "en"`, the existing Chinese text when `"zh-TW"`, and fall back to Chinese for an unrecognized/legacy value
- [X] T011 [P] [US1] Nav-shell test in `apps/web/src/app/core/nav-shell/nav-shell.component.spec.ts`: renders `<app-language-switcher>`
- [X] T012 [P] [US1] Scoreboard test in `apps/web/src/app/features/scoreboard/scoreboard.component.spec.ts`: `<app-language-switcher>` is present even in the `loading`/`linkInvalidated`/error branches, not only after `courtInfo()` resolves
- [X] T013 [P] [US1] Control-panel test in `apps/web/src/app/features/control-panel/control-panel.component.spec.ts`: `<app-language-switcher>` is present even in the `loading`/`linkInvalidated`/error branches
- [X] T014 [P] [US1] All-courts control-panel test in `apps/web/src/app/features/control-panel/all-courts/all-courts-control-panel.component.spec.ts`: `<app-language-switcher>` is present even in the `loading`/`linkInvalidated`/error branches

### Implementation for User Story 1

- [X] T015 [US1] Create `apps/web/src/assets/i18n/en.json` with a full English translation for every key currently in `apps/web/src/assets/i18n/zh-TW.json` (530 leaf keys, identical key structure — FR-001, SC-001)
- [X] T016 [US1] Fix FR-008 in `apps/web/src/app/features/member/settings/settings.component.html`: replace the hardcoded `member.settings.basic.languageZhTW` key in the `@for` loop with the per-option display-name lookup (depends on T009, T007)
- [X] T017 [US1] Embed `<app-language-switcher>` in `apps/web/src/app/core/nav-shell/nav-shell.component.html` (depends on T011, T007)
- [X] T018 [P] [US1] Add a standalone `<app-language-switcher>` placed before the `@if (linkInvalidated()) {...}` chain in `apps/web/src/app/features/scoreboard/scoreboard.component.html`, styled so it doesn't crowd the distance-readable score display in `apps/web/src/app/features/scoreboard/scoreboard.component.scss` (depends on T012, T007; Edge Case spec.md:62)
- [X] T019 [P] [US1] Add a standalone `<app-language-switcher>` placed before the `@if (linkInvalidated()) {...}` chain in `apps/web/src/app/features/control-panel/control-panel.component.html` (depends on T013, T007)
- [X] T020 [P] [US1] Add a standalone `<app-language-switcher>` placed before the `@if (linkInvalidated()) {...}` chain in `apps/web/src/app/features/control-panel/all-courts/all-courts-control-panel.component.html` (depends on T014, T007)
- [X] T021 [US1] Add a per-language `(subject, body_template)` mapping and language-aware selection (defaulting unknown values to `zh-TW`) to `_issue_verification_token_and_email()` and `forgot_password()` in `apps/api/app/domains/member/service.py` (depends on T010; research.md #4)

**Checkpoint**: User Story 1 is fully functional and independently testable — switching to English translates the whole app, backend errors, and transactional emails; every anonymous/no-nav-shell route has its own switcher.

---

## Phase 4: User Story 2 - 語言選擇會被記住，不需要每次重新設定 (Priority: P2)

**Goal**: The chosen language survives reloads; an anonymous guest's choice is browser-local and is overridden by the member's account preference on login (never the reverse); the global switcher stays in sync with the existing 個人設定 language dropdown; a brand-new registration seeds its initial preference from the registering browser's current choice instead of always defaulting to `zh-TW`.

**Independent Test**: Switch to English, reload — still English. Log in as a member whose stored preference is `zh-TW` — account wins, no flicker. Switch again while logged in, log out — still English (US2#4). Register a new account as an English-choosing guest — new account's preference is English, not the default.

### Tests for User Story 2

- [X] T022 [P] [US2] Extend `apps/web/src/app/core/language/language.service.spec.ts`: on a successful login response, the member's `language_preference` overrides any existing localStorage/guest value (FR-003b, US2#3) — no dependency on which value was set first
- [X] T023 [P] [US2] Extend `apps/web/src/app/core/language/language.service.spec.ts`: `setLanguage()` while a member session is active also calls `AuthService.setLanguagePreference()` (FR-003c); while anonymous, it does not attempt that call
- [X] T024 [P] [US2] Backend unit test in `apps/api/tests/unit/domains/member/test_registration_validation.py`: `register()` seeds `Member.language_preference` from a valid `RegisterRequest.language`, falls back to the column default (`zh-TW`) when the field is absent, and also falls back (never raises) when the value is outside `SUPPORTED_LANGUAGES`
- [X] T025 [P] [US2] Backend contract test in `apps/api/tests/contract/test_register.py`: `POST /members/register` accepts an optional `language` field and the created member's `language_preference` reflects it
- [X] T026 [P] [US2] Test in `apps/web/src/app/features/auth/register/register.component.spec.ts`: `submit()` includes `language: this.translate.currentLang()` in the register payload
- [X] T027 [P] [US2] Extend `apps/web/src/app/core/language/language.service.spec.ts`: logging out does NOT reset the current-language signal or clear the localStorage key — the browser keeps showing whatever language was active immediately before logout (US2 Acceptance Scenario 4)

### Implementation for User Story 2

- [X] T028 [US2] In `apps/web/src/app/core/language/language.service.ts`, implement: (a) the login-success override — re-resolve from the fresh `member.language_preference`, superseding any existing localStorage/guest value (depends on T022); (b) `setLanguage()` also calling `AuthService.setLanguagePreference()` whenever a member session is active, satisfying FR-003c (depends on T023); (c) logout leaving the current-language signal and localStorage untouched (depends on T027)
- [X] T029 [P] [US2] Add optional `language: str | None = None` to `RegisterRequest` in `apps/api/app/domains/member/schemas.py`, validated against `SUPPORTED_LANGUAGES` (invalid/missing → ignored, never a 4xx)
- [X] T030 [P] [US2] Add optional `language?: string` to `RegisterRequest` in `apps/web/src/app/core/api/member-auth.models.ts`
- [X] T031 [US2] Use the validated `language` value (falling back to the existing column default) when constructing the `Member` in `register()`, `apps/api/app/domains/member/service.py` (depends on T024, T025, T029)
- [X] T032 [US2] Pass `language: this.translate.currentLang()` into the register payload in `apps/web/src/app/features/auth/register/register.component.ts` (depends on T026, T030)

**Checkpoint**: User Stories 1 AND 2 both work independently — persistence, login/logout precedence, cross-device sync (pre-existing 022 behavior, unaffected), and new-registration seeding all verified.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T033 [P] Run `specs/024-add-english-language/quickstart.md` end-to-end against the local Docker Compose stack (all 7 scenarios + regression checks)
- [X] T034 Full regression pass: backend `ruff check` + `mypy --strict` + `pytest`; frontend `ng lint` + `ng build --configuration development` + `ng test --watch=false` — zero regressions, zero residual references to `languageZhTW` as a universal label

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup (T001) — BLOCKS both user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion. No dependency on US2.
- **User Story 2 (Phase 4)**: Depends on Foundational completion. Independent of US1's translation content (T015/T021), but shares `LanguageService` (T005) as its extension point (T028 builds on T005, not on anything US1 adds).
- **Polish (Phase 5)**: Depends on both user stories being complete.

### Parallel Opportunities

- Foundational: T002 and T004/T006 (different stacks — backend contract test vs. frontend unit tests) can run in parallel; T004→T005 and T006→T007 are each sequential pairs.
- US1: all four "Tests for User Story 1" (T009-T014) are parallel (different files). T018/T019/T020 (the three standalone-switcher placements) are parallel once T007 exists.
- US2: T022-T027 (all six tests, including the logout-retention test) are parallel (different files/frameworks). T029/T030 are parallel (backend vs. frontend model file).

---

## Parallel Example: User Story 1

```bash
# Tests, launched together:
Task: "Nav-shell renders <app-language-switcher> — nav-shell.component.spec.ts"
Task: "Scoreboard switcher visible during loading/error — scoreboard.component.spec.ts"
Task: "Control-panel switcher visible during loading/error — control-panel.component.spec.ts"
Task: "All-courts switcher visible during loading/error — all-courts-control-panel.component.spec.ts"

# Standalone-switcher placements, launched together once T007 (LanguageSwitcherComponent) exists:
Task: "Add switcher to scoreboard.component.html"
Task: "Add switcher to control-panel.component.html"
Task: "Add switcher to all-courts-control-panel.component.html"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1).
2. **STOP and VALIDATE**: run quickstart.md Scenarios 1, 2, 6, 7 — full-app English translation, no-nav-shell switchers, localized emails, per-option labels.
3. This alone satisfies the feature's stated primary value (spec.md "Why this priority" for US1) even before persistence/precedence (US2) lands.

### Incremental Delivery

1. Setup + Foundational → infrastructure ready, no visible change.
2. Add US1 → validate independently → English is usable app-wide (MVP).
3. Add US2 → validate independently → the choice sticks and behaves correctly around login/logout/registration.
4. Polish → full regression + quickstart replay.

---

## Notes

- [P] tasks touch different files with no unmet dependency.
- Tests are written before their corresponding implementation task per Constitution II; each task is done only when its test(s) pass and the full suite (backend + frontend) stays green.
- T015 (the `en.json` translation itself) is the single largest task by volume but has no sub-task dependencies of its own — it can start as soon as Phase 2 lands.
- Avoid: editing `zh-TW.json` content in this feature (unchanged, per SC-004 — existing users see zero change).
