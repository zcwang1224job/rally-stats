# UI Contract: `NavShellComponent`

**Feature**: [spec.md](../spec.md) | **Data model**: [data-model.md](../data-model.md)

**Revision 2026-09-08a**: row 2 narrowed — the shell no longer renders
`/member/settings`/`/member/match-history`/`/friends` directly. Signed-in
users reach those via the 會員專區 hub (`/member`, itself redesigned with
card menu rows) instead of duplicating them in the top bar. Ad-hoc change,
not run through a full `/speckit-specify` cycle.

**Revision 2026-09-08b**: row 5 (logout) removed from this component
entirely — the action itself still exists, just relocated to a standalone
button on the member hub page (`member.component`), not duplicated here.
`NavShellComponent` no longer injects `Router` or calls `AuthService.logout()`.

**Revision 2026-09-08c**: row 7 narrowed further — `groups/new`,
`groups/reauth`, `groups/:groupId/join`, `join/:token`, and
`guest-access/:token` no longer opt out via `data.navShell: false`; every
"normal" page in the app now shows the top bar (plus a breadcrumb trail,
see `apps/web/src/app/core/breadcrumb/`). Only the three full-screen
courtside/projector displays (`scoreboard/:courtToken`,
`control/:courtToken`, `control/all/:allCourtsToken`) still opt out — see
the corrected Non-goals bullet below (this doc previously and incorrectly
also listed `groups/:groupId/admin`/`groups/:groupId/member-view` there;
those two never actually had `navShell: false` in `app.routes.ts`, so the
top bar has always rendered on them regardless of what this doc said).

This project has no external API surface for this feature (pure front-end,
see research.md). The "contract" here is the component's observable
behavior — what any consumer (a route, a test, a future page) can rely on.

## Component identity

- Selector: `app-nav-shell`
- Location: `apps/web/src/app/core/nav-shell/nav-shell.component.ts`
- Standalone, no `@Input()`/`@Output()` — it is fully self-contained
  (reads `AuthService.loggedIn` directly), matching how
  `group-member-view`'s existing bottom nav is self-contained rather than
  parameterized by its host.

## Behavioral contract

| # | Given | Then | Traces to |
|---|-------|------|-----------|
| 1 | `AuthService.loggedIn()` is `false` | Shell shows: home link, groups link, login link, register link. No nickname, no logout, no member sub-links render. | FR-002, spec US1 scenario 1 |
| 2 | `AuthService.loggedIn()` is `true` | Shell shows: home link, groups link, member-home link. No login/register, no logout, no settings/match-history/friends links render (all reachable instead via the 會員專區 hub at `/member`, which also owns the logout button now). | FR-002, FR-007, spec US1 scenario 2, US3 scenario 1 |
| 3 | Viewport width `< 768px` | Shell renders as a compact bar with a single toggle control; the full link list is hidden until the toggle is activated, then appears as a collapsible panel. | FR-003, spec US1 scenario 1/2 |
| 4 | Viewport width `>= 768px` | Shell renders all applicable links inline, no toggle control present, nothing collapsed. | FR-003, spec US1 scenario 2 |
| 5 | ~~User activates the logout action~~ | **Removed (2026-09-08b)** — logout is no longer part of this component; see the member hub page instead. | ~~FR-006~~ |
| 6 | Any rendered link is activated | Standard `routerLink` navigation occurs; no full page reload. | FR-004, FR-007 |
| 7 | Host route's resolved `data.navShell` is explicitly `false` | `App` root does not render `<app-nav-shell>` at all for that route. | FR-009, FR-010, research.md Decision 2 |

## Non-goals (explicitly out of contract)

- `NavShellComponent` never renders on `scoreboard/:courtToken`,
  `control/:courtToken`, `control/all/:allCourtsToken` — full-screen
  courtside/projector displays with no chrome (Revision 2026-09-08c).
  `groups/:groupId/admin` and `groups/:groupId/member-view` DO render it —
  member-view also layers its own bottom nav on top, and admin-page adds a
  single plain link, but neither opts out of the top bar itself.
- No new backend endpoint, no new request/response DTO — `logout()` is a
  purely local state change (clears stored tokens); it does not call the
  API.

## Test expectations (for the Tasks phase)

A `nav-shell.component.spec.ts` MUST assert rows 1, 2, and 6 above via
`TestBed` + a stubbed/real `AuthService` (toggle the signal, assert rendered
links via `fixture.nativeElement.querySelectorAll`). Row 3/4 (viewport
width) cannot be asserted meaningfully under jsdom (no real layout/media
query evaluation) — verify those visually per quickstart.md instead, same
approach already used for 008-sport-minimalist-ui's breakpoint work.
