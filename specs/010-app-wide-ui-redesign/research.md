# Phase 0 Research: 全站介面重新設計

**Feature**: [spec.md](./spec.md)
**Date**: 2026-09-02

No `[NEEDS CLARIFICATION]` markers exist in spec.md (the two scope-defining
questions were resolved directly with the user before drafting). This phase
documents the architectural decisions needed to execute the spec's 7 user
stories against the current codebase, plus one real constitution conflict
found in the source mockup that must be resolved before implementation.

## Current-state survey

- **Scoreboard** (`apps/web/src/app/features/scoreboard/`): already renders
  score + names + a `next-up` badge (`state.next_up`) — the "即將登場" data
  is already available from the backend; this story is presentation-only.
- **Control panel** (`apps/web/src/app/features/control-panel/`): each team
  column currently stacks score above its `+1`/`-1` buttons; no per-court
  "下一場" button exists today — see Decision 3 below for why the mockup's
  version of that button cannot be built as literally drawn.
- **Admin page** (`apps/web/src/app/features/group-admin/admin-page/`): a
  single long scrolling page with every section (settings form, scoring
  form, PIN, links, schedule/roster) always rendered — confirmed by reading
  the full component this session.
- **Group browse list** (`apps/web/src/app/features/group-join/group-list/`):
  `GroupListComponent` already tracks `page`/`totalPages` signals from the
  API response, but the template never renders any pagination control, and
  the card omits `match_mode`/activity time even though the API returns
  them (per `GroupListItem`) — this is a template gap, not a missing API.
- **Auth forms** (register/login/forgot-password): plain `<form class="form">`,
  not wrapped in `.card`, not centered — confirmed by reading
  `register.component.html` earlier this session.
- **Friend domain** (`apps/api/app/domains/friend/`): `models.py` (DB model)
  and `schemas.py` (all request/response shapes) are complete and match
  `specs/006-member-friends/data-model.md` and `contracts/friends-api.md`
  exactly. `service.py` and `router.py` are empty stubs (docstring/import
  only, zero functions). The `friend_requests` table migration
  (`ebde39e08b3a_member_auth_and_friend_tables.py`) is already applied to
  the dev database — confirmed via `\dt` on the running container. **US7's
  backend work is pure business logic + endpoint wiring against an
  already-finished schema and contract — no new data modeling.**
- **`GET /members/me/groups`, `POST /groups/{id}/forgot-admin-pin`**:
  contracts already fully specified in
  `specs/006-member-friends/contracts/{member-api,forgot-admin-pin-api}.md`;
  neither is implemented in `apps/api/app/domains/member/` or
  `apps/api/app/domains/group/` yet (grep confirms no matching route).
- **009's nav shell** (`apps/web/src/app/core/nav-shell/`): already renders
  a member-only link set (home/settings/match-history/logout); adding 好友
  and 我的團 entries there is a small, additive change to that one
  component, not a new navigation mechanism.

## Decision 1: Scoreboard gets new, component-scoped dark-theme tokens; nothing else does

**Decision**: Add a small set of new CSS custom properties scoped to
`scoreboard.component.scss` only (e.g. `--scoreboard-bg: #000`,
`--scoreboard-team-a-bg: #d80073` / `--scoreboard-team-a-border: #a50040`,
`--scoreboard-team-b-bg: #0050ef` / `--scoreboard-team-b-border: #001dbc`,
matching the drawio's exact colors). These are **not** added to the global
`:root` in `_tokens.scss` — every other screen (admin page, control panel,
join flow, member pages, home) keeps 008's existing light "運動簡約風"
tokens unchanged, per spec.md's own Assumptions.

**Rationale**: Re-reading the drawio precisely: only the 計分板 page has a
`fillColor=#000000` background shape; the 控制板 page's shapes have no
custom fill at all (default/light). So the dark theme is genuinely scoped
to one screen in the source mockup itself — this isn't a judgment call to
narrow the visual scope, it's what the mockup actually shows once read
carefully.

**Alternatives considered**:
- *Add scoreboard tokens to the global `:root`*: rejected — they'd be dead
  weight on every other page and invite accidental reuse outside the one
  screen they're designed for.
- *Reconcile 008's light theme and this dark theme into one unified system*:
  rejected — no such reconciliation is asked for by the mockup (which never
  puts both styles on the same screen), and forcing one would be solving a
  problem the design doesn't actually have.

## Decision 2: Admin page becomes a tab-shell wrapping today's existing sections, not a rewrite

**Decision**: `AdminPageComponent`'s template is restructured into a left
nav (場地／賽程／輪替名單／團名／管理權限資訊／管理員設定) plus a right
content area gated by an `activeSection` signal and `@switch`, mirroring the
exact pattern `GroupMemberViewComponent` already uses for its own tab
switching (005-member-view, `@switch (activeTab())`). Every existing
section's markup, form bindings, and TS methods move as-is into their new
`@case` branch — none of the underlying logic (forms, dialogs, service
calls) changes.

**Rationale**: Constitution VI (modularity) and the spec's own Assumption
("既有業務邏輯...一律不變，僅改變其呈現方式") both point the same direction:
this is a container/layout change, not a logic change. Reusing an
already-established tab-switching pattern from this same codebase (rather
than introducing a new one, e.g. a router-based sub-navigation) keeps the
admin page consistent with `group-member-view`'s own internal navigation
idiom.

**Alternatives considered**:
- *Child routes per tab (`/groups/:id/admin/courts`, `/admin/schedule`,
  ...)*: rejected — adds router complexity (more entries needing the
  009 `navShell: false` exclusion, deep-linking edge cases) for a page whose
  tabs are pure client-side view state, not independently linkable resources;
  no requirement in spec.md asks for deep-linkable tabs.

## Decision 3: The mockup's per-court "下一場" control-panel button is not built as drawn — Constitution IV conflict

**Decision**: The redesigned control panel keeps exactly the two actions it
has today — `+1`/`-1` per team and "提前結束" (end match early) — repositioned
per FR-005 (buttons flanking the score). The mockup's extra "下一場" button
per court is **not implemented**.

**Rationale**: Constitution IV is explicit: "無需驗證即可開啟的畫面（單一場地
控制板、全部場地控制板...）MUST NOT 提供任何管理員專屬操作（例如 Next
Round...）" — Next Round is named in the constitution itself as the
canonical example of an admin-only action forbidden on this exact screen.
The only "next round" concept that exists today is group-wide (admin page's
"Next Round"/"Auto Next Round", per-group not per-court) and is correctly
gated to the PIN-authenticated admin page. Building a per-court "下一場"
button on the no-auth control panel would mean either (a) silently exposing
a new admin-only capability on an unauthenticated surface — a direct
Constitution IV violation — or (b) inventing new unspecified semantics for
what a "per-court next match" even means outside the group's round-based
scheduling model, which spec.md does not define and no existing FR supports.
Neither is acceptable; omitting the button is the only option that keeps
faith with both the constitution and the actual current scheduling model.
This is documented here (and in plan.md's Constitution Check) rather than
silently dropped, so it reads as a deliberate, justified deviation from the
source mockup, not an oversight.

**Alternatives considered**:
- *Build it as a group-wide "Next Round" trigger, just relocated to the
  control panel*: rejected outright — this is the literal violation
  Constitution IV names by example.
- *Ask the user to amend the constitution to allow it*: out of scope for
  this planning pass — no signal in the spec or the user's own scoping
  answers asked for a constitutional change, and `/speckit-constitution` is
  a separate, explicit process this feature does not invoke.

## Decision 4: Join-flow password/nickname steps become an in-page modal, not new routes

**Decision**: `JoinFlowComponent`'s existing `password`/`nickname`/`confirm`
steps (currently full-page, switched via its `step` signal) get a centered
modal presentation (a `<dialog>`-based overlay, consistent with the
`<app-confirm-dialog>` pattern already established in 008) instead of
replacing the whole page per step. The component's own step-machine logic,
validation, and API calls are unchanged — only the container markup around
each step changes.

**Rationale**: The mockup shows the password/nickname entry as a centered
card floating over the (dimmed) list behind it, not as a full page
navigation — this matches a modal, not a route. Reusing the existing
`<dialog>` idiom (native element, already keyboard/focus-accessible per its
008 implementation) is more consistent than inventing a second overlay
mechanism for what is visually the same kind of "centered card over
content" interaction already used elsewhere in this app.

**Alternatives considered**:
- *Keep as full-page steps, just add centering CSS*: rejected — doesn't
  match the mockup's explicit floating-card-over-dimmed-background
  composition (the drawio shows the list page's shapes still present
  behind the password/nickname card).

## Decision 5: Friends system frontend structure and route plan

**Decision**: New `apps/web/src/app/features/friends/` directory with three
route-level components:
- `friend-list/` → `/friends` (好友列表: filter, paginate, "新增" button to
  the add-friend screen; per contract `GET /friends`)
- `friend-add/` → `/friends/add` (新增好友: search by `user_number`, shows
  the four-state button/label per `friendship_status`, "發送好友申請"; per
  `GET /members/search`, `POST /friends/requests`)
- `friend-requests/` → `/friends/requests` (回覆好友申請: incoming list,
  接受/拒絕; per `GET /friends/requests/incoming`,
  `POST /friends/requests/{id}/accept|reject`)

All three carry `data: { navShell: true }` implicitly (no exclusion needed —
they're ordinary member-area pages per 009's default) and get an entry in
`NavShellComponent`'s member-only link list (`nav.friends` → `/friends`).

**Rationale**: This mirrors the existing `apps/web/src/app/features/member/`
structure (one directory per member-area concern, one route each) rather
than cramming search/list/requests into a single mega-component with
internal tab state — friend search and friend list are independently
reachable, bookmarkable actions per the mockup (separate pages, not tabs of
one screen), unlike the admin page's tabs (Decision 2), which are views of
one resource (one group) rather than three distinct actions.

**Alternatives considered**:
- *One `FriendsComponent` with internal tabs (like the admin-page shell)*:
  rejected — unlike the admin page's tabs (all views of the *same* group),
  友新增/回覆申請/列表 are three separate user actions the mockup itself
  draws as three separate screens with their own "返回"-style navigation,
  not sub-views of one entity.

**Friend-request notifications**: the mockup's "通知 - 收到好友申請" screen
is **not** built as a push/toast notification system — `contracts/friends-api.md`
itself defines no such mechanism (no Ably event, explicitly: "MUST NOT 對
另一方發送任何通知"), and spec.md's FR-015 only requires the incoming list
to be visible and actionable, not proactively pushed. The incoming-request
count is surfaced simply: `/friends/requests` shows whatever `GET
/friends/requests/incoming` currently returns when visited. No new
real-time infrastructure is introduced for this feature.

## Decision 6: `我的團` (my-groups) + forgot-admin-pin lives under `member/`, linked from the member home menu

**Decision**: `apps/web/src/app/features/member/my-groups/` (path already
named this way in 006's own pending task T046 — reused verbatim), routed at
`/member/my-groups`, linked from `MemberComponent`'s (US6's redesigned)
menu alongside 對戰紀錄/好友/個人設定.

**Rationale**: The mockup's explicit "會員資訊" screens only show
對戰紀錄/好友/個人設定/登出 as menu items, but 006's spec (already-approved,
this feature only finishes it) requires a 我的團 + 忘記管理PIN碼 entry point
somewhere reachable from the member area. Placing it as a fifth menu item
alongside the mockup's four is the smallest deviation that satisfies both
sources — same menu-list visual pattern, one more row.

## Summary of Constitution-relevant findings

- Decision 3 is the one real conflict between the source mockup and the
  constitution; resolved by omission, documented above and re-affirmed in
  plan.md's Constitution Check.
- Everything else in this feature is layout/presentation work over
  already-approved business logic (US1-6) or the completion of
  already-fully-specified, already-schema-migrated functionality (US7) —
  no other constitutional tension was found.
