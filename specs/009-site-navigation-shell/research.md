# Phase 0 Research: 全站導覽規劃（行動裝置優先）

**Feature**: [spec.md](./spec.md)
**Date**: 2026-09-02

No `[NEEDS CLARIFICATION]` markers exist in spec.md, so this phase focuses on
resolving the concrete architectural decisions the spec deliberately left to
`/speckit-plan` (see spec.md Assumptions, last bullet), plus surveying the
current codebase to ground those decisions in what actually exists today.

## Current-state survey

- `apps/web/src/app/app.ts` / `app.html`: root shell is a bare
  `<router-outlet />` — there is no navigation chrome anywhere in the app
  today. This confirms the spec's premise directly.
- `apps/web/src/app/features/auth/auth.service.ts`: `AuthService.isLoggedIn()`
  reads `localStorage` synchronously on each call; it is **not** reactive
  (no Signal/Observable). No `logout()` method exists — callers would have to
  call `clearTokens()` themselves and navigate manually, and nothing today
  does this because there is no logout entry point anywhere.
- `apps/web/src/app/features/home/home.component.ts`: inline template with
  two **hardcoded Chinese-text** links ("建立揪團場次", "重新驗證管理頁") —
  this itself is a pre-existing Constitution Principle VIII violation
  (display text must live in i18n key files) that US2's rewrite will also
  fix as a side effect of replacing the template.
- `apps/web/src/app/app.routes.ts`: 19 routes across 6 feature areas, none
  carry route `data` today. No route currently opts in/out of any shared
  chrome, because no shared chrome exists.
- 008-sport-minimalist-ui already established: design tokens
  (`_tokens.scss`), `.btn`/`.card`/`.tap-target` utility classes, and the
  768px/1024px breakpoint pair. `group-member-view.component.scss` already
  has one working responsive nav pattern (`position: fixed` bottom bar on
  mobile → `position: static` top-of-content bar at ≥768px) that this
  feature's shell can follow structurally, without touching that component.

## Decision 1: Reactive login-state signal on `AuthService`

**Decision**: Add a public `readonly loggedIn: Signal<boolean>` to
`AuthService`, backed by a private `WritableSignal` initialized from
`getAccessToken() !== null`, flipped to `true` in `setTokens()` (called by
`login()` and `changePassword()`) and to `false` in a new `logout(): void`
method (which calls `clearTokens()` then updates the signal — it does not
navigate; the nav shell component decides where to send the user after).

**Rationale**: FR-002/FR-006 require the shell to reflect login state and to
update immediately after logout without a page reload. A plain method read on
every render would work but gives Angular's change detection nothing to key
off when nothing else on screen changes (e.g. logging out from
`member/settings` where the rest of the page also disappears/redirects, but
in general navigating away is not guaranteed to always re-render the shell
otherwise). A signal makes the shell's auth-dependent branch reactive for
free wherever it's already used in a template with `@if`/`@else`.

**Alternatives considered**:
- *Poll `isLoggedIn()` on a timer*: rejected, wasteful and adds latency to a
  state change that is already known at the exact call site that causes it.
- *`BehaviorSubject` instead of Signal*: rejected for consistency — this
  codebase already uses Signals as its reactive primitive throughout
  (008's components, `group-member-view`), not RxJS subjects for local UI
  state.

## Decision 2: Route inclusion — which pages get the shell

**Decision**: The shell renders on exactly the routes FR-001 lists by
function: home (`''`), group browse (`groups`), all three member-area routes
(`member`, `member/settings`, `member/match-history`), and all five auth
routes (`auth/register`, `auth/login`, `auth/forgot-password`,
`auth/reset-password/:token`, `auth/verify-email/:token`).

It does **not** render on:
- `groups/:groupId/member-view` (FR-009, explicit — already has its own
  008-era bottom nav).
- `scoreboard/:courtToken`, `control/:courtToken`,
  `control/all/:allCourtsToken` (FR-010, explicit — deep-link/QR
  courtside screens).
- `groups/:groupId/admin` (FR-008 gives it one dedicated "return to home"
  link instead of the full shell — admin identity is a per-group PIN
  session, not a member login, so the shell's login-state section would be
  meaningless there).
- `join/:token`, `groups/:groupId/join`, `groups/new`, `groups/reauth` —
  these are not named in FR-001's page list. `join/:token` is grouped with
  the other QR/deep-link entry points in spec.md's Edge Cases ("加入連結...
  透過 QR Code 或深連結開啟的頁面"). `groups/:groupId/join` is its
  post-redirect continuation, reached only from that same deep link, so it
  inherits the same minimal-chrome treatment. `groups/new` and
  `groups/reauth` are short, single-purpose forms reached from the home
  hub's own CTA buttons (US2) — adding the full shell on top of a form whose
  own "cancel"/back action is a home link would duplicate navigation, so
  they stay chrome-free like the deep-link pages, consistent with
  Constitution VI (don't couple unrelated concerns onto one page).

**Rationale**: This gives every route an unambiguous, spec-traceable answer
instead of an implicit default, and keeps the shell scoped to exactly the
"browse and manage your own membership" surface the four user stories
describe.

**Alternatives considered**:
- *Show the shell everywhere by default, opt out per-route*: rejected —
  inverts the burden of proof; FR-001 already enumerates an inclusion list,
  so mirroring that list directly in code is less error-prone than trying to
  remember every exclusion.

**Mechanism**: Angular route `data: { navShell: false }` on the excluded
routes (default is shown; only mark exclusions, since inclusions are the
common case and match FR-001's explicit list almost one-to-one). `App`
(root component) subscribes to `Router` `NavigationEnd` events, walks
`ActivatedRoute.snapshot` to the deepest child's `data`, and derives a
`showNavShell: Signal<boolean>` gating `<app-nav-shell>` in `app.html`.

## Decision 3: Shell layout — hamburger below 768px, persistent bar at ≥768px

**Decision**: A single `NavShellComponent`, fixed to the top of the viewport.
Below 768px it collapses to a compact bar (home link + hamburger toggle
button) that expands a dropdown/drawer of the remaining links on tap. At
≥768px (`tokens.$breakpoint-tablet` and up — no separate 1024px behavior
needed here since FR-003 only calls out two states, mobile vs. tablet/
desktop) it renders as a persistent horizontal bar with all links visible,
no toggle button.

**Rationale**: FR-003 requires exactly this two-state behavior. Following
008's precedent (`group-member-view`'s bottom nav, which is fixed-position
on mobile and static/inline at the tablet breakpoint) keeps the pattern
consistent across the app rather than inventing a second nav idiom.

**Alternatives considered**:
- *Sidebar/drawer-from-left on all sizes*: rejected — heavier interaction
  (overlay + backdrop + focus trap) than the content justifies for ~6 links,
  and doesn't match the lightweight bottom-nav precedent already in the app.
- *Bottom placement (like group-member-view) instead of top*: rejected for
  the global shell specifically — the member-view bottom nav is scoped to
  one feature's own 4 actions; a global shell needs to always show a brand/
  home affordance, which reads more conventionally at the top of the
  screen, and top placement avoids any visual collision on the pages where
  a feature might later want its own bottom nav.

## Decision 4: Logout is not a "destructive action" under Principle V

**Decision**: Logout does not go through the two-step `<app-confirm-dialog>`
pattern used for disband/kick/regenerate-PIN elsewhere in the app.

**Rationale**: Constitution V's confirmation requirement is scoped to
"具破壞性或不可逆影響" (destructive or irreversible) actions — its own
rationale section is about accidental data loss from a mis-tap. Logging out
loses no data and is trivially reversible (log back in); SC-002 also
explicitly bounds logout to "at most 2 taps," which a confirmation step
would violate. Documented here so this isn't mistaken for an oversight
during review.

## Decision 5: Member-area sub-navigation reuses the one global shell

**Decision**: US3 ("會員專區內部導覽") is satisfied by the same
`NavShellComponent` instance already rendering on `member`,
`member/settings`, and `member/match-history` — its logged-in branch links
directly to all three routes plus logout. No second, member-scoped nav
component is introduced.

**Rationale**: FR-007 only requires that these three pages be reachable from
each other without detouring through `member` first; the global shell already
satisfies that the moment it lists all three as peer links. Building a
second nav component for the same three routes would duplicate markup/tests
for no behavioral gain and violate Constitution VI (module boundaries should
map to distinct concerns, not be multiplied without one).

**Alternatives considered**:
- *Separate `MemberSubNavComponent` rendered only inside the three member
  pages*: rejected as redundant with the global shell's own link list.

## Decision 6: Admin page back-link is a plain in-page element, not the shell

**Decision**: `admin-page.component.html` gets one small, i18n'd
"返回首頁" link (styled `.btn--secondary` or plain anchor with
`.tap-target`, `routerLink="/"`) placed near the page's existing title —
not the `NavShellComponent`.

**Rationale**: Decision 2 already excludes this route from the shell (the
shell's login/logout affordances are meaningless for a PIN-authenticated
admin session). FR-008 only requires *a* way back to home, not the full
shell, and its own acceptance scenario confirms this return action must not
touch the group's PIN/token validity — a plain link has no interaction with
auth state at all, which trivially satisfies that constraint.

## Summary of files this plan will touch

No backend, database, or API contract changes — confirmed pure front-end
scope per spec.md's own Assumptions. See plan.md Project Structure for the
concrete file list.
