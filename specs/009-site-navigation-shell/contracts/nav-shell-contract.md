# UI Contract: `NavShellComponent`

**Feature**: [spec.md](../spec.md) | **Data model**: [data-model.md](../data-model.md)

**Revision 2026-09-08**: row 2 narrowed — the shell no longer renders
`/member/settings`/`/member/match-history`/`/friends` directly. Signed-in
users reach those via the 會員專區 hub (`/member`, itself redesigned with
card menu rows) instead of duplicating them in the top bar. Ad-hoc change,
not run through a full `/speckit-specify` cycle.

This project has no external API surface for this feature (pure front-end,
see research.md). The "contract" here is the component's observable
behavior — what any consumer (a route, a test, a future page) can rely on.

## Component identity

- Selector: `app-nav-shell`
- Location: `apps/web/src/app/core/nav-shell/nav-shell.component.ts`
- Standalone, no `@Input()`/`@Output()` — it is fully self-contained
  (reads `AuthService.loggedIn` and `Router` directly), matching how
  `group-member-view`'s existing bottom nav is self-contained rather than
  parameterized by its host.

## Behavioral contract

| # | Given | Then | Traces to |
|---|-------|------|-----------|
| 1 | `AuthService.loggedIn()` is `false` | Shell shows: home link, groups link, login link, register link. No nickname, no logout, no member sub-links render. | FR-002, spec US1 scenario 1 |
| 2 | `AuthService.loggedIn()` is `true` | Shell shows: home link, groups link, member-home link, logout action. No login/register, settings/match-history/friends links render (reachable instead via the 會員專區 hub at `/member`). | FR-002, FR-007, spec US1 scenario 2, US3 scenario 1 |
| 3 | Viewport width `< 768px` | Shell renders as a compact bar with a single toggle control; the full link list is hidden until the toggle is activated, then appears as a collapsible panel. | FR-003, spec US1 scenario 1/2 |
| 4 | Viewport width `>= 768px` | Shell renders all applicable links inline, no toggle control present, nothing collapsed. | FR-003, spec US1 scenario 2 |
| 5 | User activates the logout action | `AuthService.logout()` is called; `loggedIn()` flips to `false` synchronously; the shell's own link list re-renders to the guest set in the same frame (no navigation performed by `logout()` itself); host then navigates to `/` or `/auth/login`. | FR-006, spec US1 scenario 3, US3 scenario 2, SC-002 |
| 6 | Any rendered link is activated | Standard `routerLink` navigation occurs; no full page reload. | FR-004, FR-007 |
| 7 | Host route's resolved `data.navShell` is explicitly `false` | `App` root does not render `<app-nav-shell>` at all for that route. | FR-009, FR-010, research.md Decision 2 |

## Non-goals (explicitly out of contract)

- `NavShellComponent` never renders on `groups/:groupId/admin`,
  `groups/:groupId/member-view`, `scoreboard/:courtToken`,
  `control/:courtToken`, `control/all/:allCourtsToken` — those pages get
  either their own existing nav (member-view) or a single plain link
  (admin-page), not this component. See research.md Decisions 2 and 6.
- No new backend endpoint, no new request/response DTO — `logout()` is a
  purely local state change (clears stored tokens); it does not call the
  API.

## Test expectations (for the Tasks phase)

A `nav-shell.component.spec.ts` MUST assert rows 1, 2, 5, and 6 above via
`TestBed` + a stubbed/real `AuthService` (toggle the signal, assert rendered
links via `fixture.nativeElement.querySelectorAll`). Row 3/4 (viewport
width) cannot be asserted meaningfully under jsdom (no real layout/media
query evaluation) — verify those visually per quickstart.md instead, same
approach already used for 008-sport-minimalist-ui's breakpoint work.
