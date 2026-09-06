# Implementation Plan: 全站介面重新設計（依 ScoreBoardUI.drawio 視覺藍圖）

**Branch**: `010-app-wide-ui-redesign` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/010-app-wide-ui-redesign/spec.md`

## Summary

Seven user stories, each mapping to one page of `ui/ScoreBoardUI.drawio`:
redesign the scoreboard (dark theme, giant colored score panels) and
control panel (dual/multi-court single-page layout, repositioned +1/-1),
restructure the admin page into a left-nav tab shell, restyle the home page
into an icon nav, restyle the join-flow into a card list + modal steps,
restyle the member auth pages into centered cards — all six of these are
presentation-only changes over already-working business logic. The
seventh finishes the already-approved-but-half-built `006-member-friends`
spec (friend search/list/requests, my-groups + forgot-admin-pin), whose
data model and API contracts already exist and are already migrated; this
feature writes the missing service/router code and all of its frontend.

One real conflict was found and resolved during planning: the mockup's
per-court "下一場" button on the control panel is not implemented, because
it would expose an admin-only capability (Next Round) on an unauthenticated
screen, which Constitution IV names explicitly as forbidden. See
research.md Decision 3.

## Technical Context

**Language/Version**: TypeScript 5.9 (Angular 20 standalone + Signals) for
all frontend work; Python 3.12 (FastAPI, SQLAlchemy 2.0 async, Pydantic v2)
for User Story 7's backend work.

**Primary Dependencies**: No new dependencies. Reuses `@ngx-translate/core`,
existing `AuthService`/`GroupAdminService`/`GroupJoinService`/
`GroupMemberViewService`, 008's design tokens (`_tokens.scss`, `.btn`/
`.card`/`.tap-target`), 009's `NavShellComponent`, the existing
`ConfirmDialogComponent` (`<dialog>`-based), and — for User Story 7 —
FastAPI's existing `optional_member`/`require_member`/`require_verified_member`
dependencies and the already-migrated `friend_requests` table.

**Storage**: PostgreSQL — **zero new tables or migrations** (data-model.md).
User Story 7 is pure application code against an already-migrated schema.

**Testing**: Vitest (`@angular/build:unit-test`) for frontend; pytest for
backend (unit/contract/integration, per this project's existing three-tier
convention under `apps/api/tests/`).

**Target Platform**: Web browser, mobile/tablet-first (existing 768px/
1024px breakpoints; admin page's new left nav must collapse below 768px
per FR-008).

**Project Type**: Web application — both `apps/web` (all 7 stories) and
`apps/api` (User Story 7 only).

**Performance Goals**: No new performance requirements beyond what's
already established (Ably ~1s sync for scoreboard/control panel, unchanged
by this feature); admin-page tab switching must feel instant (client-side
signal flip, no network round-trip per switch, per SC-003).

**Constraints**: No new admin-only capability may be exposed on any
no-auth screen (Constitution IV) — this directly shaped Decision 3. All new
User Story 7 endpoints MUST match `specs/006-member-friends/contracts/`
exactly, not be redesigned. All new visible text MUST go through the
existing i18n key convention (Constitution VIII). Scoreboard's new dark
theme tokens MUST stay scoped to that one component (research.md Decision 1).

**Scale/Scope**: This is the largest spec authored in this project to
date — 7 user stories, ~15-20 existing frontend components restyled, 1
component (`AdminPageComponent`) restructured, 3 new frontend routes/
components for friends + 1 for my-groups, and 6 new backend endpoints
(`GET /members/search`, `GET /members/me/groups`, `POST
/groups/{id}/forgot-admin-pin`, `GET /friends`, `POST /friends/requests`,
`GET /friends/requests/incoming`, `POST /friends/requests/{id}/accept`,
`POST /friends/requests/{id}/reject`, `DELETE /friends/{id}` — 9 total)
implemented against an already-fully-specified contract.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design —
Decision 3 (research.md) was made specifically to keep this gate clean;
no other changes were needed after design.*

| Principle | Applies? | How this feature complies |
|---|---|---|
| I. 型別安全 | Yes | All new/moved TypeScript and Python code stays under existing `strict`/`mypy --strict` settings; no `any`, no type-ignore. |
| II. 測試優先（核心領域邏輯） | Yes (US7 only) | User Story 7 adds real domain logic (friend request state machine, forgot-PIN token issuance) — MUST have unit test coverage for the state transitions (`pending→accepted/rejected`, `accepted→unfriended`, uniqueness-conflict → `FRIEND_REQUEST_ALREADY_PENDING`) per Constitution II, mirrored in tasks.md. US1-6 touch no domain logic (presentation-only), so this principle doesn't gate them. |
| III. 即時性與資料一致性 | Yes (bounded) | US1/US2 (scoreboard/control panel) keep the existing Ably subscription and score-authority model completely unchanged — this feature only restyles already-correct real-time UI. US7's forgot-admin-pin reuses the exact same `link.regenerated`/`admin` broadcast + token-version-invalidation pattern `regenerate-admin-pin` already uses (per `specs/006-member-friends/contracts/forgot-admin-pin-api.md`) — no new consistency model invented. |
| IV. 權限與安全 | Yes (this is the gate that mattered most) | Decision 3: the mockup's per-court "下一場" control-panel button is excluded because it would violate the "no admin-only action on no-auth screens" rule verbatim. US7's new endpoints all require `require_verified_member` per their existing contracts — no new auth mechanism, no relaxation of the email-verification gate. |
| V. UX 一致性（破壞性操作二次確認） | Yes | 解除好友 (unfriend) and 忘記管理 PIN 碼 (invalidates the current PIN immediately) both get the existing `<app-confirm-dialog>` two-step pattern — both are irreversible-enough actions (PIN reset can't be undone; unfriending requires a fresh request to reverse) to warrant it, consistent with how disband/kick/regenerate-PIN already work. |
| VI. 可維護性（模組化） | Yes | Admin page becomes a tab shell reusing `group-member-view`'s already-established `@switch`-on-signal pattern (Decision 2) rather than inventing a new one. Friends gets its own `features/friends/` module, one component per independent action, not a monolith (Decision 5). |
| VII. 無障礙與行動裝置優先 | Yes | Admin page's new left nav MUST collapse below 768px (FR-008) and every new interactive element (nav items, friend action buttons, my-groups reset buttons) meets the 44×44px minimum via existing `.tap-target`/`--touch-target-min` tokens. Scoreboard's dark theme keeps the offline banner's existing non-color-only status indicator (icon/text, not color alone). |
| VIII. 多語系與時區架構 | Yes | Every new visible string (admin section labels, friend-screen copy, my-groups labels) goes into `zh-TW.json` via the `translate` pipe — no hardcoded text, matching this project's established convention. |
| IX. 可攜性與可部署性 | No | No new environment variables, no Docker/build changes. |
| X. 即時同步可信來源 | Yes (bounded) | Unchanged for US1-6 (scoreboard/control panel already server-authoritative). Friends explicitly has **no** real-time channel (contract: no Ably event on unfriend/accept/reject) — this feature must not add one un-asked-for. |
| XI. 防機器人/防濫用 | No (bounded) | `GET /members/search` already has its own per-IP rate limit defined in `specs/006-member-friends/research.md` #6 (reused, not redesigned here) — no new Turnstile-gated "create resource" endpoint is introduced by this feature. |

No unresolved violations — Complexity Tracking below documents the one
deliberate mockup deviation (Decision 3) and the feature's unusual size,
both by design, not by accident.

## Project Structure

### Documentation (this feature)

```text
specs/010-app-wide-ui-redesign/
├── plan.md                          # This file
├── research.md                      # Phase 0 output — 6 decisions
├── data-model.md                    # Phase 1 output — reused entities + AdminSection view-model
├── quickstart.md                    # Phase 1 output — 7 validation scenarios
└── contracts/
    ├── reused-api-contracts.md      # Points US7 at 006's existing API contracts
    ├── admin-page-contract.md       # US3 tab-shell behavioral contract
    ├── scoreboard-control-panel-contract.md  # US1/US2 behavioral contract
    └── friends-frontend-contract.md # US7 frontend routes + behavioral contract
```

### Source Code (repository root)

```text
apps/web/src/
├── app/
│   ├── app.routes.ts                       # MODIFY: add /friends, /friends/add,
│   │                                        #   /friends/requests, /member/my-groups
│   ├── core/nav-shell/
│   │   └── nav-shell.component.{ts,html}   # MODIFY: add 好友 link (member-only)
│   ├── features/
│   │   ├── scoreboard/
│   │   │   └── scoreboard.component.{html,scss}     # MODIFY (US1): dark theme, big panels
│   │   ├── control-panel/
│   │   │   ├── control-panel.component.{html,scss}  # MODIFY (US2): buttons flank score
│   │   │   └── all-courts/
│   │   │       └── all-courts-control-panel.component.scss  # MODIFY (US2): stacked layout
│   │   ├── group-admin/admin-page/
│   │   │   ├── admin-page.component.ts     # MODIFY (US3): add AdminSection signal
│   │   │   ├── admin-page.component.html   # MODIFY (US3): left-nav + @switch shell
│   │   │   └── admin-page.component.scss   # MODIFY (US3): sidebar layout + mobile collapse
│   │   ├── home/
│   │   │   └── home.component.{html,scss}  # MODIFY (US4): icon-based nav
│   │   ├── group-join/
│   │   │   ├── group-list/
│   │   │   │   └── group-list.component.{html,scss} # MODIFY (US5): pagination UI, card fields
│   │   │   └── join-flow/
│   │   │       └── join-flow.component.{html,scss}  # MODIFY (US5): modal presentation
│   │   ├── auth/
│   │   │   ├── register/register.component.{html,scss}          # MODIFY (US6): card
│   │   │   ├── login/login.component.{html,scss}                 # MODIFY (US6): card
│   │   │   └── forgot-password/forgot-password.component.{html,scss} # MODIFY (US6): card
│   │   ├── member/
│   │   │   ├── member.component.{ts,html}  # MODIFY (US6): menu-style, add 我的團 entry
│   │   │   └── my-groups/                  # NEW (US7)
│   │   │       ├── my-groups.component.ts
│   │   │       ├── my-groups.component.html
│   │   │       ├── my-groups.component.scss
│   │   │       └── my-groups.component.spec.ts
│   │   └── friends/                        # NEW directory (US7)
│   │       ├── friends.service.ts          # NEW: API layer for all 6 friend/member-search endpoints
│   │       ├── friend-list/
│   │       ├── friend-add/
│   │       └── friend-requests/
│   │           # each: *.component.{ts,html,scss,spec.ts}
│   └── assets/i18n/zh-TW.json               # MODIFY: new keys for every restyled/new screen
apps/api/src (app.domains):
├── member/
│   ├── router.py                            # MODIFY (US7): add /members/search, /members/me/groups
│   └── service.py                           # MODIFY (US7): implement both
├── group/
│   ├── router.py                            # MODIFY (US7): add /groups/{id}/forgot-admin-pin
│   └── service.py                           # MODIFY (US7): implement (reuses regenerate_admin_pin core logic)
└── friend/
    ├── router.py                            # MODIFY (US7): implement all 6 endpoints (currently empty)
    └── service.py                           # MODIFY (US7): implement all business logic (currently empty)
```

**Structure Decision**: Everything lives in the two existing projects
(`apps/web`, `apps/api`) — no new top-level project. User Stories 1-6 touch
only existing files (pure restyle/restructure). User Story 7 adds exactly
one new frontend directory (`features/friends/`) and one new frontend
component (`features/member/my-groups/`) — both following this codebase's
existing "one directory per feature area" convention — plus implementation
bodies for already-declared backend router/service files.

## Complexity Tracking

> Filled per Constitution Check note above — both entries are deliberate,
> justified, not oversights.

| Deviation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Mockup's per-court "下一場" control-panel button is not built (research.md Decision 3) | Building it as drawn would expose an admin-only capability (Next Round) on an unauthenticated screen, violating Constitution IV verbatim | Relocating the existing group-wide "Next Round" here instead of the admin page was considered — rejected because Constitution IV names exactly this action as the forbidden example, not because of any UX preference |
| This one spec covers 7 user stories / two full layers (frontend + backend) instead of being split into several smaller specs | The user explicitly confirmed this scope ("整個 App 都要重做", "這次一起做" for friends) via `AskUserQuestion` before drafting spec.md — both were pure scope decisions with no inferable default, not a planning-stage judgment call | Splitting into 7 separate `/speckit-specify` features was considered and rejected per the user's explicit choice; tasks.md (next phase) organizes work by user story specifically so each of the 7 remains independently deliverable despite living in one spec |
