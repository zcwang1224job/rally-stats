# Tasks: 全站介面重新設計（依 ScoreBoardUI.drawio 視覺藍圖）

**Input**: Design documents from `specs/010-app-wide-ui-redesign/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included for User Story 7 only — it introduces real domain logic (friend request state machine, forgot-PIN token issuance), which Constitution Principle II requires test coverage for. User Stories 1-6 are presentation-only over already-tested business logic, so no new test tasks are generated for them (matches this project's existing convention from 008-sport-minimalist-ui, which also skipped jsdom tests for pure visual/breakpoint changes) — verify those via `quickstart.md` instead.

**Organization**: Tasks are grouped by user story (US1-US7, priorities per spec.md) to enable independent implementation and testing of each.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Frontend paths are under `apps/web/src/`; backend paths under `apps/api/`

---

## Phase 1: Setup

- [X] T001 [P] Create `apps/web/src/app/features/friends/` and `apps/web/src/app/features/member/my-groups/` directories (empty, ready for US7's Phase 9 files)

---

## Phase 2: Foundational

**None** — unlike this project's prior features, no infrastructure here blocks *all* seven stories at once: US1-6 each restyle one already-working, independent component, and US7's shared prerequisite (a new `FriendsService` API client) only blocks *other tasks within US7 itself*, not the other six stories — so it lives as the first task of Phase 9 instead of here. User Story phases below can proceed in any order once Setup is done.

---

## Phase 3: User Story 1 - 計分板重新設計 (Priority: P1) 🎯 MVP

**Goal**: Dark background, giant colored team score panels, stacked participant names, repositioned "即將登場" badge.

**Independent Test**: Open any court's scoreboard link in singles and doubles mode; confirm dark background, two-color panels, correct name stacking, and next-up badge presence/absence per quickstart.md Scenario 1.

- [X] T002 [P] [US1] Add scoreboard-only dark-theme + team-color CSS custom properties (`--scoreboard-bg`, `--scoreboard-team-a-bg`/`-border`, `--scoreboard-team-b-bg`/`-border`) to `apps/web/src/app/features/scoreboard/scoreboard.component.scss` (research.md Decision 1 — scoped to this component only, not `_tokens.scss`)
- [X] T003 [US1] Restructure `apps/web/src/app/features/scoreboard/scoreboard.component.html`: dark background container, two large colored score panels (team A left/magenta, team B right/blue) each showing that team's score in a very large font and stacked participant nicknames beneath it; reposition the existing `next-up status-badge` element into a screen corner. Data bindings (`match.score_a`/`score_b`, `match.participants`, `state.next_up`) are unchanged — only markup/CSS. (Depends on T002.)
- [X] T004 [P] [US1] Create `apps/web/src/app/features/scoreboard/scoreboard.component.spec.ts`: doubles match renders 2 nicknames per team panel, singles renders 1; `state.next_up` present renders the badge, absent does not; offline banner (`common.offlineBanner`) still renders when `connectionState() !== 'connected'`.

**Checkpoint**: US1 fully functional and testable independently.

---

## Phase 4: User Story 2 - 控制板重新設計 (Priority: P1)

**Goal**: Single-page multi-court layout; per-court score centered with `+1`/`-1` flanking it left/right; no per-court "下一場" button.

**Independent Test**: Open the all-courts control panel with 2+ active courts; confirm every court's block is visible without switching pages, button placement matches FR-005, and no "下一場" element exists anywhere (research.md Decision 3) — per quickstart.md Scenario 2.

- [X] T005 [US2] Update `apps/web/src/app/features/control-panel/control-panel.component.html` + `.scss`: center the score, move team A's `+1`/`-1` to the left of it and team B's to the right, keep "提前結束" below; do **not** add any "下一場"/next-match element (research.md Decision 3, Constitution IV — this is a deliberate exclusion)
- [X] T006 [P] [US2] Update `apps/web/src/app/features/control-panel/all-courts/all-courts-control-panel.component.scss` (and its court-block sub-component's scss if styling lives there) so multiple active courts stack vertically on one page with no pagination/tab-switching between them
- [X] T007 [US2] Update `apps/web/src/app/features/control-panel/control-panel.component.spec.ts` (existing file): assert the new button-placement structure (left/right button groups relative to the score element) and assert no element matching a "下一場"/next-match action exists in the rendered template. (Depends on T005.)

**Checkpoint**: US1 and US2 both work independently.

---

## Phase 5: User Story 3 - 開團管理頁改為側邊欄式導覽 (Priority: P1)

**Goal**: Left-nav tab shell (場地/賽程/輪替名單/團名/管理權限資訊/管理員設定) replacing the single long scrolling page, with zero change to any underlying action.

**Independent Test**: Open any group's admin page; click through all 6 left-nav items and confirm each existing action (新增場地, Next Round, 重新產生 PIN 碼, 解散, etc.) still works from its new location; confirm read-only (disbanded) mode still renders the shell — per quickstart.md Scenario 3, and per `contracts/admin-page-contract.md`.

- [X] T008 [US3] Add an `AdminSection` type (`'courts' | 'schedule' | 'roster' | 'name' | 'access' | 'settings'`, data-model.md) and an `activeSection = signal<AdminSection>('courts')` to `apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts`
- [X] T009 [US3] Restructure `admin-page.component.html` into a left-nav (6 items, `(click)` sets `activeSection`) + `@switch (activeSection())` content area; move each existing section's markup (settings form → `name`+`settings` cases, scoring form → `settings` case, PIN/regenerate → `access` case, links/QR → `courts` case, schedule/roster block → `schedule`/`roster` cases) into its corresponding `@case` unchanged — no form binding, dialog, or service call may be altered, only relocated. (Depends on T008.)
- [X] T010 [US3] Update `admin-page.component.scss`: persistent vertical sidebar at `>= 768px` (tokens.$breakpoint-tablet), collapsing to a horizontally-scrollable strip or expandable menu below it (FR-008), all nav items meeting the 44×44px `--touch-target-min`
- [X] T011 [P] [US3] Add `adminPage.section.{courts,schedule,roster,name,access,settings}` i18n keys to `apps/web/src/assets/i18n/zh-TW.json`
- [X] T012 [US3] Update `admin-page.component.spec.ts` (existing file): default `activeSection` is `'courts'`; clicking each nav item switches the rendered content; `view.read_only: true` still renders all 6 nav items with each section's existing read-only content. (Depends on T009.)

**Checkpoint**: US1, US2, and US3 all work independently — this closes out the P1 (highest-priority) scope.

---

## Phase 6: User Story 4 - 首頁改版 (Priority: P2)

**Goal**: Top nav becomes icon-based (嘎團/開團/登入 or member entry), logic unchanged from 009.

**Independent Test**: Open `/` as guest and as a logged-in member; confirm icon-based nav renders the correct entries per login state — per quickstart.md Scenario 4.

- [X] T013 [US4] Update `apps/web/src/app/features/home/home.component.html` + `.scss`: replace the current `.btn`-styled text links with an icon-based top nav row (icon + short label), keeping the existing `loggedIn()`-conditional branch from 009 unchanged
- [X] T014 [P] [US4] Update `apps/web/src/app/features/home/home.component.spec.ts` (existing file, from 009): adjust assertions if the icon markup changes the queried elements' structure, keeping the same guest/member link-set coverage

**Checkpoint**: US1-4 all work independently.

---

## Phase 7: User Story 5 - 嘎團／加入流程改版 (Priority: P2)

**Goal**: Card-based group list with working pagination and richer card fields; password/nickname/confirm steps become a centered modal.

**Independent Test**: Browse groups with filters and multiple pages; join a password-protected group as both guest and member — per quickstart.md Scenario 5, per `research.md` Decision 4.

- [X] T015 [US5] Update `apps/web/src/app/features/group-join/group-list/group-list.component.html` + `.scss`: render Previous/page-number/Next controls wired to the already-tracked `page`/`totalPages` signals (currently tracked in TS but never rendered); add `match_mode` and activity-time fields to each card (already present on `GroupListItem`, just not displayed today)
- [X] T016 [P] [US5] Create `apps/web/src/app/features/group-join/group-list/group-list.component.spec.ts`: pagination controls render correctly for `totalPages > 1` and are absent for `totalPages === 1`; new card fields render from the existing API response fields
- [X] T017 [US5] Convert `apps/web/src/app/features/group-join/join-flow/join-flow.component.html`'s `password`/`nickname`/`confirm` steps to render inside a centered `<dialog>`-based modal (reusing the `<app-confirm-dialog>` idiom already established in 008) in `join-flow.component.{html,scss}` — the component's existing step-signal logic, validation, and API calls are unchanged, only the container markup changes
- [X] T018 [P] [US5] Create `apps/web/src/app/features/group-join/join-flow/join-flow.component.spec.ts`: each step renders inside the modal container; a logged-in member skips the nickname step straight to confirm, a guest does not (per existing `isMember` branch)

**Checkpoint**: US1-5 all work independently.

---

## Phase 8: User Story 6 - 會員頁面版面改版 (Priority: P2)

**Goal**: Centered card forms for register/login/forgot-password; menu-style member home page.

**Independent Test**: Walk through register/login/forgot-password/first-login-nickname and the member home menu; confirm card layout and that all 5 menu rows are present and correctly linked — per quickstart.md Scenario 6.

- [X] T019 [P] [US6] Wrap `apps/web/src/app/features/auth/register/register.component.html` in a centered `.card`
- [X] T020 [P] [US6] Wrap `apps/web/src/app/features/auth/login/login.component.html` in a centered `.card`
- [X] T021 [P] [US6] Wrap `apps/web/src/app/features/auth/forgot-password/forgot-password.component.html` in a centered `.card`
- [X] T022 [US6] Restructure `apps/web/src/app/features/member/member.component.{ts,html}` into a menu-style list of rows — 對戰紀錄 (`/member/match-history`), 好友 (`/friends`), 我的團 (`/member/my-groups`), 個人設定 (`/member/settings`), and a 登出 action (reusing `AuthService.logout()` from 009) — replacing whatever the current member home renders
- [X] T023 [P] [US6] Create `apps/web/src/app/features/member/member.component.spec.ts`: all 5 rows render with the correct `routerLink`/click action

**Checkpoint**: US1-6 all work independently — every presentation-only story is now complete.

---

## Phase 9: User Story 7 - 完成好友系統與會員團記錄復原功能 (Priority: P3)

**Goal**: Finish `006-member-friends`'s still-open backend (US4-6 there) and build its entirely-missing frontend, styled per this feature's design. All request/response shapes, error codes, and detailed acceptance scenarios are defined in `specs/006-member-friends/` (see `contracts/reused-api-contracts.md`) — tasks below implement against those, not against a new design.

**Independent Test**: Two verified member accounts search/friend/accept/list/unfriend each other; one member's own "my groups" forgot-PIN flow — per quickstart.md Scenario 7, per `contracts/friends-frontend-contract.md`.

### Backend — 我的團 + 忘記管理 PIN 碼

- [X] T024 [US7] Implement `GET /members/me/groups` in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py` (only `created_by_member_id == caller`, any status, per `specs/006-member-friends/contracts/member-api.md`)
- [X] T025 [US7] Implement `POST /groups/{group_id}/forgot-admin-pin` in `apps/api/app/domains/group/service.py` + `apps/api/app/domains/group/router.py` (reuses `regenerate_admin_pin`'s core logic + `require_verified_member` + creator-match check + existing `link.regenerated`/`admin` broadcast, per `contracts/forgot-admin-pin-api.md`)
- [X] T026 [P] [US7] Unit test: `GET /members/me/groups` excludes anonymously-created groups, includes disbanded ones, in `apps/api/tests/unit/domains/member/test_my_groups.py`
- [X] T027 [P] [US7] Unit test: forgot-admin-pin rejects non-creator/anonymously-created groups (`NOT_GROUP_CREATOR`), succeeds on disbanded groups, in `apps/api/tests/unit/domains/group/test_forgot_admin_pin.py`
- [X] T028 [P] [US7] Contract test for both endpoints per their contracts in `apps/api/tests/contract/test_forgot_admin_pin.py`
- [X] T029 [US7] Integration test: member creates group → forgot PIN → new token enters admin page directly (no re-entry of the shown PIN) → old PIN/token invalid → a second open admin-page session receives the `link.regenerated` broadcast within ~1s, in `apps/api/tests/integration/test_forgot_admin_pin_flow.py`. (Depends on T024, T025.)

### Backend — 搜尋與新增好友

- [X] T030 [US7] Implement `GET /members/search` (per-IP rate limit, mirroring `/groups/reauth`'s existing limiter) in `apps/api/app/domains/member/service.py` + `router.py`
- [X] T031 [US7] Implement `POST /friends/requests` in `apps/api/app/domains/friend/service.py` + `apps/api/app/domains/friend/router.py`
- [X] T032 [P] [US7] Unit test: four-state `friendship_status` logic (`none`/`pending_outgoing`/`pending_incoming`/`friends`) in `apps/api/tests/unit/domains/friend/test_search_friendship_status.py`
- [X] T033 [P] [US7] Unit test: search excludes unverified accounts, rejects searching self (`CANNOT_SEARCH_SELF`), in `apps/api/tests/unit/domains/friend/test_search_exclusions.py`
- [X] T034 [P] [US7] Unit test: pending-pair uniqueness → `FRIEND_REQUEST_ALREADY_PENDING` on the DB partial-unique-index conflict, in `apps/api/tests/unit/domains/friend/test_pending_uniqueness.py`
- [X] T035 [P] [US7] Contract test for `GET /members/search`, `POST /friends/requests` in `apps/api/tests/contract/test_friend_search.py`
- [X] T036 [US7] Integration test: A searches B → sends request → A re-searches sees "pending_outgoing", B searches A sees "pending_incoming", in `apps/api/tests/integration/test_friend_search_flow.py`. (Depends on T030, T031.)

### Backend — 好友列表、回覆邀請、解除好友

- [X] T037 [US7] Implement `GET /friends` (paginated, `nickname`/`user_number` substring filter) + `GET /friends/requests/incoming` in `apps/api/app/domains/friend/service.py` + `router.py`
- [X] T038 [US7] Implement `POST /friends/requests/{id}/accept` and `POST /friends/requests/{id}/reject` in `apps/api/app/domains/friend/service.py` + `router.py` (only the `addressee` may act; otherwise `FRIEND_REQUEST_NOT_FOUND`)
- [X] T039 [US7] Implement `DELETE /friends/{friend_request_id}` (unfriend: `accepted → unfriended`, no notification of any kind) in `apps/api/app/domains/friend/service.py` + `router.py`
- [X] T040 [P] [US7] Unit test: accept/reject state transitions, non-addressee gets `FRIEND_REQUEST_NOT_FOUND`, in `apps/api/tests/unit/domains/friend/test_respond_friend_request.py`
- [X] T041 [P] [US7] Unit test: reject-then-resend creates a new row without modifying the old `rejected` row, in `apps/api/tests/unit/domains/friend/test_reject_then_resend.py`
- [X] T042 [P] [US7] Unit test: unfriend transition, unlimited resend afterward, no notification side-effect, in `apps/api/tests/unit/domains/friend/test_unfriend.py`
- [X] T043 [P] [US7] Unit test: friend-list nickname/user_number substring filter, in `apps/api/tests/unit/domains/friend/test_friend_list_filter.py`
- [X] T044 [P] [US7] Contract test for `GET /friends`, `GET /friends/requests/incoming`, accept, reject, `DELETE /friends/{id}` in `apps/api/tests/contract/test_friend_lifecycle.py`
- [X] T045 [US7] Integration test: A/B become mutual friends → both lists show each other → A unfriends → both lists update immediately, B receives no notification → B can resend without limit, in `apps/api/tests/integration/test_friend_lifecycle_flow.py`. (Depends on T037, T038, T039.)

### Frontend

- [X] T046 [US7] Create `apps/web/src/app/features/friends/friends.service.ts`: API client methods for all 6 friend/member-search endpoints (search, create request, list, incoming, accept, reject, unfriend), following the existing `authHeader()`-per-service pattern used by `GroupMemberViewService`/`AuthService`
- [X] T047 [P] [US7] Create `apps/web/src/app/features/friends/friend-add/friend-add.component.{ts,html,scss,spec.ts}`: search-by-`user_number` form, renders the matching button/label for each `friendship_status` value (contracts/friends-frontend-contract.md row 1-3), "發送好友申請" action. (Depends on T046, T030, T031.)
- [X] T048 [P] [US7] Create `apps/web/src/app/features/friends/friend-list/friend-list.component.{ts,html,scss,spec.ts}`: filter input, pagination, per-row "解除好友" behind a two-step `<app-confirm-dialog>` (Constitution V). (Depends on T046, T037, T039.)
- [X] T049 [P] [US7] Create `apps/web/src/app/features/friends/friend-requests/friend-requests.component.{ts,html,scss,spec.ts}`: incoming list, 接受/拒絕 actions. (Depends on T046, T037, T038.)
- [X] T050 [P] [US7] Create `apps/web/src/app/features/member/my-groups/my-groups.component.{ts,html,scss,spec.ts}`: lists `GET /members/me/groups`, per-row "忘記管理 PIN 碼" behind a two-step `<app-confirm-dialog>` (Constitution V — this invalidates the current PIN immediately), on success stores the new admin token via the existing `GroupAdminService.setAdminToken()` and navigates to that group's admin page. (Depends on T024, T025.)
- [X] T051 [US7] Add `/friends`, `/friends/add`, `/friends/requests`, `/member/my-groups` routes to `apps/web/src/app/app.routes.ts` (default `navShell: true`, no exclusion needed). (Depends on T047, T048, T049, T050.)
- [X] T052 [US7] Add a 好友 entry (`nav.friends` → `/friends`) to `NavShellComponent`'s member-only link list in `apps/web/src/app/core/nav-shell/nav-shell.component.{ts,html}`, plus its existing spec coverage. (Depends on T051.)
- [X] T053 [P] [US7] Add all new i18n keys (`friends.*`, `myGroups.*`, `nav.friends`) to `apps/web/src/assets/i18n/zh-TW.json`

**Checkpoint**: All 7 user stories are now independently functional — the feature is complete.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [X] T054 Run all 7 scenarios in `quickstart.md` manually against the live Docker stack (`docker compose up -d --build` in `infra/`), including verifying the "下一場" exclusion (US2) and the no-notification guarantee (US7)
- [X] T055 [P] Run `cd apps/web && npm test && npm run lint && npx tsc --noEmit`, confirming every spec added/touched in this feature passes
- [X] T056 [P] Run `cd apps/api && source .venv/bin/activate && ruff check . && mypy . && pytest`, confirming every test added in Phase 9 passes
- [X] T057 Security review (mirrors `006-member-friends` T069): confirm every new US7 endpoint requires the correct auth level (`require_verified_member`), and that no response leaks another member's email, password hash, or verification status

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: None — proceed directly to user stories.
- **User Stories (Phase 3-9)**: All independent of each other except where noted below; can proceed in any order or in parallel across different people.
- **Polish (Phase 10)**: Depends on all 7 user stories being complete.

### User Story Dependencies

- **US1, US2, US3 (all P1)**: Fully independent of each other and of every other story.
- **US4, US5, US6 (all P2)**: Fully independent of each other and of US1-3.
- **US7 (P3)**: Internally sequential in places (see task-level `Depends on` notes above — implementation before its own tests/integration, service before frontend), but has no dependency on US1-6's outcomes; its frontend does depend on 009's already-existing `NavShellComponent` and `ConfirmDialogComponent`, both already in the codebase.

### Within User Story 7 specifically

- Backend implementation tasks (T024, T025, T030, T031, T037, T038, T039) before their own unit/contract/integration tests can meaningfully pass.
- `friends.service.ts` (T046) before any of the three friend components (T047-T049).
- All four new components (T047-T050) before routing them (T051).
- Routes (T051) before the nav-shell entry that links to one of them (T052).

### Parallel Opportunities

- T002 and T004 (US1) touch different files and can run in parallel once T003 (which T004 needs, since it's testing the restructured template) is done — see task order above; T002 itself is parallel with nothing it depends on.
- T019, T020, T021 (US6, three different auth components) are fully parallel.
- Within US7's backend, every `[P]`-marked unit/contract test task touches its own file and can run in parallel with the others in the same sub-section.
- T047, T048, T049, T050 (US7 frontend components) are mutually parallel — four different component directories.
- Across stories: US1, US2, US3, US4, US5, US6 can all be staffed and executed simultaneously by different people since none of their files overlap.

---

## Parallel Example: User Story 6

```bash
Task: "Wrap register.component.html in a centered .card"
Task: "Wrap login.component.html in a centered .card"
Task: "Wrap forgot-password.component.html in a centered .card"
```

## Parallel Example: User Story 7 Frontend Components

```bash
Task: "Create friend-add/friend-add.component.{ts,html,scss,spec.ts}"
Task: "Create friend-list/friend-list.component.{ts,html,scss,spec.ts}"
Task: "Create friend-requests/friend-requests.component.{ts,html,scss,spec.ts}"
Task: "Create member/my-groups/my-groups.component.{ts,html,scss,spec.ts}"
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 3, 4, 5 (US1, US2, US3 — all P1)
3. **STOP and VALIDATE**: Run quickstart.md Scenarios 1-3
4. This alone delivers the redesign of the three highest-traffic, most
   directly mockup-derived screens (scoreboard, control panel, admin page)
   without touching anything else.

### Incremental Delivery

1. Setup → US1 → validate → deploy/demo (courtside screens redesigned)
2. Add US2 → validate → deploy/demo
3. Add US3 → validate → deploy/demo (P1 scope complete)
4. Add US4, US5, US6 (any order, all P2) → validate each → deploy/demo
   (every presentation-only screen now redesigned)
5. Add US7 (P3, largest single story) → validate → deploy/demo (feature
   complete; friends system and my-groups/forgot-PIN are now real)

### Parallel Team Strategy

With multiple developers, after Setup:
- Developer A: US1 + US2 (scoreboard/control panel — related, small)
- Developer B: US3 (admin page — largest single P1 story)
- Developer C: US4 + US5 + US6 (home/join/member — all P2, all independent)
- Developer D: US7 (friends + my-groups — largest story overall, spans
  both backend and frontend; can itself be split further per its own
  internal task dependencies above)

## Notes

- [P] tasks touch different files with no ordering dependency between them.
- US7 is the only story with generated test tasks — Constitution Principle
  II requires them for its new domain logic; US1-6 are presentation-only
  and rely on `quickstart.md` for verification instead.
- The "下一場" button from the source mockup is intentionally never built
  (US2, research.md Decision 3) — do not add it back if it's noticed
  missing during implementation.
- Commit after each task or logical group, per this project's established
  per-feature commit pattern.
- Total: 57 tasks. Setup: 1. US1: 3. US2: 3. US3: 5. US4: 2. US5: 4. US6: 5.
  US7: 30 (6 my-groups/forgot-pin, 7 friend-search, 9 friend-lifecycle, 8
  frontend). Polish: 4.
