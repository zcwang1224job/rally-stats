# Implementation Plan: 全站導覽規劃（行動裝置優先）

**Branch**: `009-site-navigation-shell` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-site-navigation-shell/spec.md`

## Summary

The app currently has zero navigation chrome — `app.html` is a bare
`<router-outlet />`, the home page has two hardcoded links, and there is no
logout entry point anywhere. This feature adds one reusable
`NavShellComponent` (top-fixed, hamburger below 768px / persistent bar at
768px+) rendered from the app root on the pages FR-001 lists (home, group
browse, all three member-area pages, all five auth pages), driven by a new
reactive `AuthService.loggedIn` signal and a new `AuthService.logout()`
method. It rewrites the home page into a real navigation hub (US2), and adds
one plain "返回首頁" link to the admin page (US4) instead of the shell,
since admin sessions are PIN-based, not member-login-based. Pages excluded
by spec (group-member-view, scoreboard, both control panels) and pages
excluded by plan-level scoping decision (admin, the join-link flow,
create-group, reauth — see research.md Decision 2) are opted out via route
`data`. Pure front-end change: no backend, database, or API contract work.

## Technical Context

**Language/Version**: TypeScript 5.9, Angular 20 (standalone components +
Signals)

**Primary Dependencies**: `@angular/router` (RouterLink, Router,
NavigationEnd, ActivatedRoute route `data`), existing `AuthService`
(`apps/web/src/app/features/auth/auth.service.ts`), `@ngx-translate/core`
(`translate` pipe — Constitution VIII), existing design tokens/utility
classes from 008-sport-minimalist-ui (`_tokens.scss`, `.btn`, `.tap-target`)

**Storage**: N/A — reads/writes only the existing `localStorage`-backed
tokens already managed by `AuthService`; no new persisted state.

**Testing**: Vitest via `@angular/build:unit-test` (existing project
convention), `TestBed` component tests. No backend tests needed (no backend
changes).

**Target Platform**: Web browser, mobile/tablet-first per Constitution VII;
reuses 008's `768px`/`1024px` breakpoint pair (only 768px is behaviorally
relevant here per FR-003 — see research.md Decision 3).

**Project Type**: Web application, frontend-only change (`apps/web`).

**Performance Goals**: Nav shell interactions (toggle open/close, link
navigation, logout) must feel instant — no network round-trip is involved in
any of them (auth state is a local signal read; `logout()` only clears local
storage).

**Constraints**: 44×44px minimum touch target (Constitution VII / 008
tokens) on every interactive nav element including the hamburger toggle; all
shell/home/admin-back-link display text MUST come from i18n keys
(Constitution VIII) — no hardcoded strings, including fixing the two
pre-existing hardcoded links on the home page as part of its rewrite; no new
backend/API surface (spec.md Assumptions).

**Scale/Scope**: 1 new shared component (`NavShellComponent`), 2 small
`AuthService` additions (`loggedIn` signal, `logout()` method), 1 route-data
opt-out convention across ~7 existing routes, 1 home-page rewrite, 1
admin-page addition (a single link), new `nav.*` i18n keys plus rewritten
`home.*` keys.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design —
no changes to this table were needed after design; all decisions in
research.md were made specifically to keep this gate clean.*

| Principle | Applies? | How this feature complies |
|---|---|---|
| I. 型別安全 | Yes | New code (`NavShellComponent`, `AuthService` additions) is plain TypeScript under existing `strict: true`; no `any`, no type assertions needed — `loggedIn` is a typed `Signal<boolean>`. |
| II. 測試優先（核心領域邏輯） | No | This feature touches navigation/UI only — no scoring, rotation, or match-result logic. No new domain-logic tests required by this principle; component tests are added anyway per the nav-shell contract's Test Expectations. |
| III. 即時性與資料一致性 | No | No scoreboard/control-panel/Ably-event code is touched. FR-010 explicitly keeps those pages exactly as they are. |
| IV. 權限與安全 | Yes (bounded) | Nav shell only ever reads existing `AuthService.loggedIn`/`isLoggedIn()` state — it introduces no new auth check, no new token type, and no change to the PIN/password/email-verification gates. The admin-page back-link is a plain route link with no auth logic of its own (research.md Decision 6), so it cannot bypass or weaken the group PIN gate (FR-008, spec.md Edge Cases last bullet). |
| V. 破壞性操作二次確認 | Yes (scoped out) | Logout is deliberately **not** treated as requiring the two-step confirm-dialog pattern — see research.md Decision 4 for the reasoning (not destructive, not irreversible, and SC-002 caps it at 2 taps). |
| VI. 可維護性（模組化） | Yes | One `NavShellComponent` lives in `apps/web/src/app/core/nav-shell/` (shared/core layer, not inside any single feature module) and is reused as-is for US1/US3 rather than duplicated per page (research.md Decision 5); it has no dependency on any feature module's internals, only on `AuthService` and `Router`. |
| VII. 無障礙與行動裝置優先 | Yes | Hamburger toggle and every nav link meet the 44×44px minimum touch target (reuses `--touch-target-min`/`.tap-target` from 008). Login-state is conveyed via link presence/text, not color alone, satisfying the non-color-only rule by construction (there's no color-coded status indicator in this component at all). |
| VIII. 多語系與時區架構 | Yes | Every new visible string (`nav.*`, rewritten `home.*`, admin-page's back-link label) is added to `zh-TW.json` and rendered via the `translate` pipe — including fixing the two hardcoded strings already on the home page. No new timestamps or time-zone-sensitive data are introduced. |
| IX. 可攜性與可部署性 | No | No new environment variables, no Docker/build changes — this is application code only. |
| X. 即時同步可信來源 | No | No Ably events, no scoreboard/schedule state, are read or written by this feature. |
| XI. 防機器人/防濫用 | No | No new "create resource" public endpoint is introduced; `logout()` doesn't call the API at all. |

No violations to record — Complexity Tracking table below is intentionally
empty.

## Project Structure

### Documentation (this feature)

```text
specs/009-site-navigation-shell/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── nav-shell-contract.md   # Phase 1 output
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
apps/web/src/
├── app/
│   ├── app.ts                          # MODIFY: subscribe to Router NavigationEnd,
│   │                                    #   derive showNavShell signal from route data
│   ├── app.html                        # MODIFY: conditionally render <app-nav-shell>
│   ├── app.spec.ts                     # MODIFY: cover shell show/hide per route data
│   ├── app.routes.ts                   # MODIFY: add `data: { navShell: false }` to the
│   │                                    #   excluded routes (research.md Decision 2)
│   ├── core/
│   │   └── nav-shell/                  # NEW directory
│   │       ├── nav-shell.component.ts
│   │       ├── nav-shell.component.html
│   │       ├── nav-shell.component.scss
│   │       └── nav-shell.component.spec.ts
│   └── features/
│       ├── auth/
│       │   ├── auth.service.ts         # MODIFY: add `loggedIn` signal + `logout()`
│       │   └── auth.service.spec.ts    # MODIFY: cover the new signal/method
│       ├── home/
│       │   ├── home.component.ts       # MODIFY: real hub, i18n'd, auth-state aware
│       │   ├── home.component.html     # NEW: split out of the inline template
│       │   ├── home.component.scss     # MODIFY: layout for 4 entry points
│       │   └── home.component.spec.ts  # NEW
│       └── group-admin/admin-page/
│           ├── admin-page.component.html  # MODIFY: add one "返回首頁" link
│           └── admin-page.component.spec.ts # MODIFY: cover the new link
└── assets/i18n/
    └── zh-TW.json                      # MODIFY: add `nav.*` keys, rewrite `home.*` keys,
                                         #   add one `adminPage.backToHome` key
```

**Structure Decision**: Everything lives under the existing `apps/web`
Angular project — no new top-level project, no backend changes. The one new
component goes in `app/core/` (not under `app/features/`) because it is
shared shell chrome consumed from the app root, not a feature-scoped screen
— consistent with Constitution VI's module-boundary intent and with how
`app/core/api/` already holds cross-feature infrastructure (`ApiClient`,
shared DTOs) rather than any single feature owning it.
