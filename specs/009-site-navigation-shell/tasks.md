# Tasks: 全站導覽規劃（行動裝置優先）

**Input**: Design documents from `specs/009-site-navigation-shell/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/nav-shell-contract.md

**Tests**: Included — the nav-shell contract (`contracts/nav-shell-contract.md`) explicitly requires component-level test coverage, matching this project's existing convention (008-sport-minimalist-ui added component specs for its touch-target/layout changes).

**Organization**: Tasks are grouped by user story (US1–US4, priorities per spec.md) to enable independent implementation and testing of each.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- All paths are under `apps/web/src/`

---

## Phase 1: Setup

**Purpose**: No new dependencies or project scaffolding needed — this feature reuses the existing Angular/Vitest/ngx-translate toolchain and 008's design tokens as-is.

- [X] T001 Create the `app/core/nav-shell/` directory (empty, ready for Phase 3 files)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure both US1 and US2 depend on — the reactive login-state signal, the i18n keys every subsequent task will use, and the route-level opt-out convention that keeps the shell off the pages it must never appear on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Add `readonly loggedIn: Signal<boolean>` (backed by a private `WritableSignal` initialized from `getAccessToken() !== null`) and a new `logout(): void` method (calls `clearTokens()`, sets the signal to `false`) to `app/features/auth/auth.service.ts`; flip the signal to `true` inside the existing `setTokens()` call sites. Update `app/features/auth/auth.service.spec.ts` to cover: signal starts `false` with no stored token, flips `true` after `login()`/`setTokens()`, flips `false` after `logout()`.
- [X] T003 [P] Add the new i18n key namespace to `assets/i18n/zh-TW.json`: `nav.home`, `nav.groups`, `nav.login`, `nav.register`, `nav.memberHome`, `nav.settings`, `nav.matchHistory`, `nav.logout`, `nav.menuToggle` (aria-label), rewritten `home.*` keys for the four home-page entry points (browse groups / create group / login / register / go-to-member-area), and `adminPage.backToHome`.
- [X] T004 [P] Add `data: { navShell: false }` to these routes in `app/app.routes.ts` (research.md Decision 2): `groups/:groupId/admin`, `groups/:groupId/member-view`, `scoreboard/:courtToken`, `control/:courtToken`, `control/all/:allCourtsToken`, `join/:token`, `groups/:groupId/join`, `groups/new`, `groups/reauth`. All other existing routes keep the shell by default (no `data` needed on them).

**Checkpoint**: `AuthService` is reactive, i18n keys exist, and every route already knows whether it wants the shell — user story implementation can now begin.

---

## Phase 3: User Story 1 - 全站導覽殼層與登入狀態感知 (Priority: P1) 🎯 MVP

**Goal**: A single reusable nav shell that shows guest vs. member links correctly, collapses to a hamburger below 768px, and lets a member log out from it.

**Independent Test**: Per spec.md — open the app at mobile and tablet widths, verify guest/member link sets and login/logout behavior, without needing US2/US3/US4.

### Tests for User Story 1

- [X] T005 [P] [US1] Write `app/core/nav-shell/nav-shell.component.spec.ts` covering nav-shell-contract.md rows 1, 2, 5, 6: guest state shows home/groups/login/register only; member state shows home/groups/member-home/settings/match-history/logout only (no login/register); activating logout calls `AuthService.logout()` and the guest link set re-renders in the same test; each rendered link has the expected `routerLink`. (Write first; it will fail until T006 exists.)
- [X] T006 [P] [US1] Update `app/app.spec.ts` to cover: for a route whose resolved `data.navShell` is `false`, `<app-nav-shell>` is absent from the rendered `App`; for a route without that flag (or `navShell: true`), it is present. (Write first; will fail until T007.)

### Implementation for User Story 1

- [X] T007 [US1] Implement `NavShellComponent` (`app/core/nav-shell/nav-shell.component.ts` + `.html` + `.scss`): standalone component, no inputs/outputs, injects `AuthService` and `Router`; renders the guest/member link sets per data-model.md's `NavItem` table; renders a hamburger toggle + collapsible panel below `tokens.$breakpoint-tablet` and an inline persistent bar at/above it (reuse `--touch-target-min`, `.tap-target`, `_tokens.scss` per 008); logout button calls `authService.logout()` then `router.navigateByUrl('/')`. (Depends on T002, T003, T005.)
- [X] T008 [US1] Wire the app root: in `app/app.ts`, subscribe to `Router` `NavigationEnd` events, walk `ActivatedRoute.snapshot` to the deepest child's `data.navShell`, expose a `showNavShell: Signal<boolean>` (default `true` when the flag is absent); in `app/app.html`, wrap the existing `<router-outlet />` with `@if (showNavShell()) { <app-nav-shell /> }`. (Depends on T004, T007, T006.)

**Checkpoint**: User Story 1 is fully functional and testable independently — the shell appears/disappears correctly per route and reflects login state.

---

## Phase 4: User Story 2 - 首頁作為導覽樞紐 (Priority: P1)

**Goal**: The home page itself becomes a real hub with all four entry points, auth-state aware.

**Independent Test**: Per spec.md — open the home page as guest and as a logged-in member, verify the four (or three, when logged in) entry points independently of US1/US3/US4.

### Tests for User Story 2

- [X] T009 [P] [US2] Create `app/features/home/home.component.spec.ts`: guest state renders links to `/groups`, `/groups/new`, `/auth/login`, `/auth/register`; logged-in state renders `/groups`, `/groups/new`, and a single `/member` entry, with no login/register links. (Write first; will fail until T010.)

### Implementation for User Story 2

- [X] T010 [US2] Rewrite `app/features/home/home.component.ts` to use a split `home.component.html` template (create this file), reading `AuthService.loggedIn` to conditionally render the login/register pair vs. the single member-area entry; replace both pre-existing hardcoded-Chinese links with `nav.*`/`home.*` i18n keys via the `translate` pipe. Update `app/features/home/home.component.scss` for the four-entry-point layout (mobile-first, `.tap-target` sizing). (Depends on T002, T003, T009.)

**Checkpoint**: User Stories 1 and 2 both work independently.

---

## Phase 5: User Story 3 - 會員專區內部導覽 (Priority: P2)

**Goal**: Confirm the member-area pages are all directly reachable from each other (via the shell built in US1) with no detour, and that logout works from any of them.

**Independent Test**: Per spec.md — from `/member/match-history`, switch directly to `/member/settings` via the shell and log out from there, without needing US2/US4.

**Note**: Per research.md Decision 5, this story does not introduce a new component — it is satisfied by `NavShellComponent` (US1) already listing all three member routes as peer links. Its tasks add the missing verification coverage for that specific claim.

### Tests for User Story 3

- [X] T011 [US3] Extend `app/core/nav-shell/nav-shell.component.spec.ts` (from US1) with assertions specific to FR-007: when logged in, all three of `/member`, `/member/settings`, `/member/match-history` are simultaneously present as links (not nested/conditional on which member page is currently active), and the logout action is present and functional regardless of which member route is the current one. (Depends on T007.)

**Checkpoint**: All member-area pages are mutually reachable through the one shared shell; no separate sub-nav component was needed.

---

## Phase 6: User Story 4 - 團管理頁的返回路徑 (Priority: P2)

**Goal**: The admin page gets its own simple way back to home, without gaining the full login-aware shell.

**Independent Test**: Per spec.md — from a group's admin page, use the "返回首頁" link, then re-verify the group's PIN gate still applies on a fresh visit; independent of US1/US2/US3.

### Tests for User Story 4

- [X] T012 [P] [US4] Update `app/features/group-admin/admin-page/admin-page.component.spec.ts`: assert a `routerLink="/"` element with the `adminPage.backToHome` translated label is present; assert `<app-nav-shell>` is not rendered on this route (covered at the `App` level by T006/T004, but add a component-level assertion here that the admin page itself renders no shell-specific elements). (Write first; will fail until T013.)

### Implementation for User Story 4

- [X] T013 [US4] Add the "返回首頁" link (`routerLink="/"`, `.tap-target`, `adminPage.backToHome` i18n key) to `app/features/group-admin/admin-page/admin-page.component.html`, near the existing page title. No auth-state logic — plain link only, per research.md Decision 6. (Depends on T003, T004, T012.)

**Checkpoint**: All four user stories are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Whole-feature validation across all four stories together.

- [X] T014 Run all 5 scenarios in `quickstart.md` manually in a browser at both mobile (<768px) and tablet/desktop (≥768px) widths, including Scenario 5's confirmation that group-member-view, scoreboard, and both control-panel pages remain shell-free and visually unchanged (SC-004).
- [X] T015 [P] Run `cd apps/web && npm test && npm run lint && npx tsc --noEmit` and confirm all pass, including every spec touched/added in T002, T005, T006, T009, T011, T012.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001 is trivial and unblocking) — BLOCKS all user stories.
- **User Stories (Phase 3–6)**: All depend on Foundational (Phase 2) completion.
  - US1 and US2 (both P1) have no dependency on each other and can proceed in parallel.
  - US3 depends on US1's `NavShellComponent` (T007) existing — it only adds verification, not new implementation.
  - US4 has no dependency on US1/US2/US3 — it never touches the shell.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Within Each User Story

- Tests are written first and must fail before their corresponding implementation task.
- US1: tests (T005, T006) → component (T007) → app-root wiring (T008).
- US2: test (T009) → implementation (T010).
- US3: extends US1's existing spec file (T011) — no separate implementation task.
- US4: test (T012) → implementation (T013).

### Parallel Opportunities

- T002, T003, T004 (Foundational) touch three different files and can run in parallel.
- T005 and T006 (US1 tests) touch different spec files and can run in parallel.
- Once Foundational is done, US1, US2, and US4's test tasks (T005/T006, T009, T012) can all start in parallel; US3 (T011) must wait for T007.
- T015 (automated checks) can run alongside T014 (manual quickstart pass) since they don't touch the same artifacts.

---

## Parallel Example: Foundational Phase

```bash
Task: "Add loggedIn signal + logout() to app/features/auth/auth.service.ts"
Task: "Add nav.*/home.*/adminPage.backToHome keys to assets/i18n/zh-TW.json"
Task: "Add data: { navShell: false } to excluded routes in app/app.routes.ts"
```

## Parallel Example: User Story 1 Tests

```bash
Task: "Write app/core/nav-shell/nav-shell.component.spec.ts"
Task: "Update app/app.spec.ts for route-based shell visibility"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run quickstart.md Scenario 1 and 2 manually
5. This alone gives every page in the app its first working way back to home and its first logout entry point — the biggest gap this feature exists to close.

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. Add US1 → validate independently → this is already a usable improvement (MVP)
3. Add US2 → home page becomes a real hub → validate independently
4. Add US3 → verify member-area cross-navigation → validate independently
5. Add US4 → admin page gets its return path → validate independently
6. Polish: full quickstart pass + lint/typecheck/test suite

## Notes

- [P] tasks touch different files with no ordering dependency between them.
- No backend/API tasks exist in this feature — confirmed pure front-end scope (plan.md Summary, research.md).
- Commit after each task or logical group, per this project's established per-feature commit pattern.
- Total: 15 tasks. US1: 4 (T005–T008). US2: 2 (T009–T010). US3: 1 (T011). US4: 2 (T012–T013). Foundational: 3 (T002–T004). Setup: 1 (T001). Polish: 2 (T014–T015).
