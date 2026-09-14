# Implementation Plan: 新增英文語系

**Branch**: `024-add-english-language` | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/024-add-english-language/spec.md`

## Summary

Add English as a second selectable display language, translating the app's
entire existing text surface (screens + backend-driven error messages +
transactional emails). Introduce a global, always-visible language switcher
usable by anonymous visitors (synced to browser storage) and by logged-in
members (synced to the existing `language_preference` member setting from
022), including on the three nav-shell-less anonymous court/scoreboard
routes. No new database schema: the existing `language_preference` column
and `SUPPORTED_LANGUAGES` code-constant already support adding `"en"`. The
one backend-facing change is making the supported-languages list readable
without authentication (needed by anonymous visitors and the 3 no-login
routes), plus localizing the two transactional email templates and seeding
a new member's initial `language_preference` from the registering browser's
current choice.

## Technical Context

**Language/Version**: TypeScript 5 / Angular 20 (frontend, `apps/web`); Python 3.12 / FastAPI (backend, `apps/api`)

**Primary Dependencies**: `@ngx-translate/core` + `@ngx-translate/http-loader` (already in use, single `zh-TW.json` today), SQLAlchemy 2.0 + asyncpg (existing `Member.language_preference` column), existing `send_email()` abstraction in `apps/api/app/core/email.py`

**Storage**: PostgreSQL — no schema change. `members.language_preference` (`VARCHAR(8) NOT NULL DEFAULT 'zh-TW'`) already exists from 022; `en` is just a new accepted value in the code-level `SUPPORTED_LANGUAGES` tuple.

**Testing**: `pytest` (backend unit/contract), Angular `ng test` (Jasmine/Karma component specs), `ng lint` + `mypy --strict` + `ruff check`

**Target Platform**: Existing web app (Docker Compose local dev, `apps/web` + `apps/api`)

**Project Type**: Web application (Angular frontend + FastAPI backend, existing monorepo layout — no new top-level structure)

**Performance Goals**: SC-002 — switching language updates visible text within 2s without a page reload (in practice: near-instant, since `ngx-translate`'s `.use()` swaps the loaded translation table client-side).

**Constraints**: FR-005 — no browser-locale auto-detection, default stays zh-TW for anyone who has never chosen. FR-003c — a logged-in member's global-switcher choice and their 個人設定 language dropdown MUST reflect one single source of truth (no divergence). No DB migration.

**Scale/Scope**: Two supported languages today (`zh-TW`, `en`). Translation content scope: the full existing `zh-TW.json` (530 leaf keys) gets an `en.json` sibling, plus the two hardcoded-Chinese email templates in `member/service.py`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Code Quality & Type Safety** — PASS. New `LanguageService`/`LanguageSwitcherComponent` are strict-mode TypeScript, no `any`. Backend email-template lookup is a typed `dict[str, tuple[str, str]]`-shaped mapping, `mypy --strict` clean.
- **II. Test-First** — PASS. New `LanguageService` (localStorage read/write, precedence logic, sync-to-backend call) and the relaxed supported-languages endpoint get unit/contract tests before/alongside implementation, per existing repo convention (tests added same-task as code, run before marking tasks done).
- **III. Real-Time Sync & Consistency** — N/A. This feature has no realtime/Ably surface.
- **IV. Authorization & Security** — PASS with a deliberate, spec-mandated relaxation: `GET /supported-languages` becomes auth-free. Content is static non-member-specific config (a list of language codes) — no privacy/security downgrade. `PATCH /members/me/language` keeps its existing `require_verified_member` gate (unchanged from 022).
- **V. UX Confirmation for Destructive Actions** — N/A. Switching language is instantly reversible, not destructive.
- **VI. Modularity** — PASS. One new `LanguageService` (`providedIn: 'root'`) owns all language-state logic; one new `LanguageSwitcherComponent` is the single reusable rendering unit embedded in 4 places (nav-shell + 3 standalone routes) rather than 4 copies of switcher markup.
- **VII. Accessibility & Mobile-First** — PASS. Switcher is a `<select>`/button group with text labels (FR-008 — each language shows its own name), not color/icon-only; placed so it doesn't crowd the scoreboard's distance-readable score display (Edge Case, spec.md:62).
- **VIII. i18n & Timezone Architecture** — Directly this feature's subject. PASS: frontend text stays centralized in per-language JSON files (adds `en.json`, no inline strings); backend continues returning semantic error codes only, translated client-side (existing behavior, unaffected); date/time format explicitly stays language-independent per Assumptions (spec.md:100) — no change to existing TIMESTAMPTZ/system-timezone handling.
- **IX. Portability & Deployability** — PASS. No new external dependency, no infra change.
- **X. Server as Source of Truth** — PASS. For a logged-in member, the server-stored `language_preference` is the source of truth on login (FR-003b — account wins over local guest choice); the frontend's localStorage value is explicitly only a fallback for anonymous sessions.
- **XI. Anti-Bot & Abuse Prevention** — N/A. No new resource-creation endpoint; the newly-public `GET /supported-languages` is a read-only static-config lookup, not a target for Turnstile (mirrors other unauthenticated read endpoints already in the codebase, e.g. court/scoreboard GETs).

No unjustified violations. Proceeding to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/024-add-english-language/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── language-api.md   # Phase 1 output
└── tasks.md               # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
apps/api/
└── app/domains/member/
    ├── router.py          # relax GET /members/me/supported-languages auth; add language field wiring to register()
    ├── schemas.py         # SUPPORTED_LANGUAGES tuple gains "en"; RegisterRequest gains optional `language`
    └── service.py         # register() seeds language_preference from request; email templates keyed by language

apps/web/src/
├── assets/i18n/
│   ├── zh-TW.json         # unchanged content, now the fallback/default table
│   └── en.json            # NEW — full English translation, same key shape
└── app/
    ├── core/
    │   ├── language/                       # NEW
    │   │   ├── language.service.ts         # current-language signal, localStorage, precedence, sync to AuthService
    │   │   └── language-switcher.component.ts/.html/.scss   # reusable switcher, own display-name map (FR-008)
    │   └── nav-shell/nav-shell.component.html   # embeds <app-language-switcher>
    ├── app.config.ts                        # app init reads LanguageService's resolved starting language instead of hardcoded 'zh-TW'
    ├── features/
    │   ├── scoreboard/scoreboard.component.html          # standalone switcher above the @if chain
    │   ├── control-panel/control-panel.component.html    # standalone switcher above the @if chain
    │   ├── control-panel/all-courts/all-courts-control-panel.component.html  # standalone switcher above the @if chain
    │   ├── auth/register/register.component.ts            # submit() passes current language into RegisterRequest
    │   └── member/settings/settings.component.html         # FR-008 fix: per-option display name instead of hardcoded languageZhTW key
    └── core/api/member-auth.models.ts        # RegisterRequest gains optional `language?: string`
```

No new top-level project/module — this extends the existing Angular/FastAPI structure.
