---
description: "Task list for 026-match-record-friend-invite"
---

# Tasks: 從對戰紀錄／即時戰況頁面加好友

**Input**: Design documents from `/specs/026-match-record-friend-invite/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/friend-invite-from-pages-api.md, contracts/privacy-setting-extension-api.md, quickstart.md

**Tests**: Included — this session's established convention (see specs/025) is tests alongside/before each implementation task, run to full-suite green before a task is considered done. Constitution II's Test-First mandate applies directly here too: the friend-request state machine and the `ParticipantSummary`/public-endpoint boundary (research.md #1) are exactly the kind of core-logic/security-boundary code the principle targets.

**Organization**: Tasks are grouped by user story (US1/US2/US3, all P1/P2/P2 per spec.md) in priority order.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unmet dependency)
- **[Story]**: US1, US2, or US3
- Paths are exact, relative to repo root

---

## Post-Implementation Redesign (2026-09-14)

After all tasks below were completed and the full regression suite was
green, the user requested a redesign of US2's entry-point placement (see
spec.md Clarifications "實作後調整" and research.md's top addendum). The
task entries below are left **unmodified** as a historical record of what
was actually built in each task — this section documents what changed
afterward instead of rewriting history.

**What changed**: US2's "加好友" entry point moved from
"目前進行中比賽的參與者旁" (current-match participants only) to "輪替
名單中所有現役團員旁" (every active roster member, regardless of match
status). Concretely, superseding T029/T032–T038 above:

- Backend (`apps/api/app/domains/schedule/service.py`,
  `schemas.py`): `member_id` is no longer added to `ParticipantSummary`
  within `build_schedule_snapshot()`'s current-match query (T035 reverted).
  Instead it's added to `RosterScheduleStatus` (a new field, same file),
  populated in the `roster` list-comprehension of the same function. The
  `current_match`/`next_up` `ParticipantSummary.member_id` now stays `None`
  the same way `_match_participants_payload()`/`court_live_state()` always
  did — one more builder joins the "never populate" set, T030/T031's
  regression intent is preserved and extended.
- `court-control.component.ts`/`.html`
  (`group-admin/schedule-management/`) fully reverted to its
  pre-feature state — no add-friend code remains there (T033/T037
  superseded).
- `member-schedule.component.ts`/`.html`
  (`group-member-view/member-schedule/`) gained a new roster-list section
  (it had none before); the add-friend button now appears there instead of
  next to `current_match.participants` (T032/T034/T036 superseded).
- `admin-page.component.ts`/`.html` (`group-admin/admin-page/`) gained the
  add-friend button next to each roster entry in its existing roster tab
  (new integration point, not covered by any task above).
- `AddFriendButtonComponent` gained `iconStyle`/`nickname` inputs (FR-016)
  — both new roster-list integrations render the icon-style button; the
  match-record integrations (US1, T026/T027) are unaffected and keep the
  text-button style.
- Test files renamed/rewritten accordingly:
  `test_schedule_snapshot.py` (roster `member_id` coverage replaces
  current-match coverage), `court-control.component.spec.ts` (deleted —
  no pre-existing tests, entirely this feature's Phase-4 creation, now
  obsolete), `member-schedule.component.spec.ts` and
  `admin-page.component.spec.ts` (rewritten/extended for the roster-list
  entries).

**Verification after the redesign**: backend `pytest` (913 passed),
`ruff check`, `mypy --strict` all clean; frontend 305/305 tests passed,
`ng lint` clean, `ng build --configuration development` succeeded. No
task IDs were added or renumbered for this redesign — see this note as
the record of the delta instead.

---

## Phase 1: Setup

**Purpose**: The one schema change everything else depends on.

- [X] T001 Create an Alembic migration adding `members.allow_friend_invite_from_match_pages` (`BOOLEAN NOT NULL DEFAULT true`) in `apps/api/alembic/versions/` (data-model.md §1, same pattern as the existing `allow_search`/`share_match_records_with_friends` columns)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Type/schema plumbing every story builds on. No behavior change yet — mirrors specs/025's Phase 2 precedent (nothing here yet reads or writes the new data).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Add `allow_friend_invite_from_match_pages: Mapped[bool]` to `Member` in `apps/api/app/domains/member/models.py` (depends on T001)
- [X] T003 [P] Add `member_id: str | None = None` to `ParticipantSummary` in `apps/api/app/domains/schedule/schemas.py` (data-model.md §2 — safe default, populated only by later story tasks in three specific, already-authenticated builder functions)
- [X] T004 [P] Add `FriendRequestCreateByMemberId`, `InviteCandidatesRequest`, `InviteCandidateStatus`, `InviteCandidatesResponse` to `apps/api/app/domains/friend/schemas.py` (data-model.md §4)
- [X] T005 [P] Add `allow_friend_invite_from_match_pages` to `PrivacySettingsRequest`, `PrivacySettingsResponse`, and `MemberPublicResponse` in `apps/api/app/domains/member/schemas.py`, and extend `PrivacySettingsRequest.check_at_least_one_field` to include the new field (data-model.md §5)
- [X] T006 [P] Add `member_id?: string | null` to the frontend `ParticipantSummary` interface in `apps/web/src/app/features/group-admin/schedule-management/schedule.models.ts`
- [X] T007 [P] Add `InviteCandidateStatus`/`InviteCandidatesResponse` TS interfaces to `apps/web/src/app/core/api/friend.models.ts`, and add `allow_friend_invite_from_match_pages: boolean` to the existing privacy-settings TS interface(s) there

**Checkpoint**: Shapes exist; nothing yet reads or writes the new column or field.

---

## Phase 3: User Story 1 - 從對戰紀錄清單直接發送好友邀請 (Priority: P1) 🎯 MVP

**Goal**: A logged-in member browsing cross-group or in-group match records can click "加好友" next to any other logged-in-member participant and send a friend request, without leaving the page or knowing their user number.

**Independent Test**: Two non-friend members who share a completed match record — from either the cross-group or in-group match-records page, click "加好友" next to the other's name; confirm a pending `FriendRequest` is created and the entry updates to a "待回覆" label; confirm the same entry on a second shared match record also shows "待回覆" (no duplicate); confirm Guest participants and the viewer's own row never show the entry.

### Tests for User Story 1

- [X] T008 [P] [US1] Regression test confirming existing `create_friend_request()` (by `user_number`) behavior is byte-for-byte unchanged after the Phase-3 refactor — extend `apps/api/tests/unit/domains/friend/test_search_friendship_status.py` or a sibling test file
- [X] T009 [P] [US1] Unit tests for `create_friend_request_by_member_id()` in new file `apps/api/tests/unit/domains/friend/test_create_friend_request_by_member_id.py`: success creates a `pending` `FriendRequest`; `MEMBER_NOT_FOUND` for a Guest-only roster id, a nonexistent id, an unverified member, and a deleted member; `CANNOT_FRIEND_SELF`; `ALREADY_FRIENDS`; `FRIEND_REQUEST_ALREADY_PENDING`
- [X] T010 [P] [US1] Contract test for `POST /friends/requests/by-member` in `apps/api/tests/contract/test_friend_lifecycle.py`: 201 + `{friend_request_id, status: "pending"}`; 404/400/409 error-code mapping per contracts/friend-invite-from-pages-api.md
- [X] T011 [P] [US1] Unit tests for `get_invite_candidates_status()` in new file `apps/api/tests/unit/domains/friend/test_invite_candidates_status.py`: correctly derives all four `friendship_status` values via existing `get_friendship_status()`; `invite_eligible` true only when `friendship_status == "none"` and target is verified/not-deleted (toggle check added later in US3, T044 — for now this task only asserts eligibility given the always-true default); a requested `member_id` with no matching member is omitted from the response, not an error
- [X] T012 [P] [US1] Contract test for `POST /friends/invite-candidates` in `apps/api/tests/contract/test_friend_lifecycle.py`
- [X] T013 [P] [US1] Unit tests: `_build_match_record_summaries()` (`apps/api/app/domains/group/service.py`) populates `ParticipantSummary.member_id` — `str(entry.id)`'s corresponding member id for a Member-linked `RosterEntry`, `None` for a Guest one — extend existing group match-records unit tests
- [X] T014 [P] [US1] Unit tests: the cross-group match-records builder in `apps/api/app/domains/member/service.py` populates `member_id` the same way — extend existing member match-records unit tests
- [X] T015 [P] [US1] Frontend tests for the new shared component in `apps/web/src/app/shared/add-friend-button/add-friend-button.component.spec.ts`: renders a clickable button when `inviteEligible`; renders the matching existing status label (`friends.alreadyFriends`/`pendingOutgoing`/`pendingIncoming`) when a relationship exists; **renders nothing — no button, no label — when `inviteEligible` is `false` and `friendshipStatus` is `none` (target has opted out and no relationship exists yet, FR-008)**; click sends the request and optimistically flips to "待回覆" on success (mirrors `friend-add.component.ts`'s existing pattern); shows an inline error on failure without changing state
- [X] T016 [P] [US1] Frontend test: `match-history.component` renders `<app-add-friend-button>` next to every participant that has a `member_id` other than the viewer's own, and renders nothing for Guest participants or the viewer's own row — `apps/web/src/app/features/member/match-history/match-history.component.spec.ts`
- [X] T017 [P] [US1] Frontend test: `group-member-view/match-records.component` same behavior, including a teammate (not just an opponent) — `apps/web/src/app/features/group-member-view/match-records/match-records.component.spec.ts`

### Implementation for User Story 1

- [X] T018 [US1] Refactor `apps/api/app/domains/friend/service.py`: extract a shared `_create_friend_request_for_addressee(session, requester_id, addressee)` core out of the existing `create_friend_request()`, with no behavior change (depends on T008)
- [X] T019 [US1] Implement `create_friend_request_by_member_id(session, requester_id, addressee_member_id)` in `apps/api/app/domains/friend/service.py`, looking up the target by id and delegating to the shared core from T018 (depends on T018, T009, T002)
- [X] T020 [US1] Implement `get_invite_candidates_status(session, viewer_id, member_ids)` in `apps/api/app/domains/friend/service.py`, reusing `get_friendship_status()` per id (depends on T011, T002)
- [X] T021 [US1] Add `POST /friends/requests/by-member` and `POST /friends/invite-candidates` to `apps/api/app/domains/friend/router.py`, both behind `require_verified_member` (depends on T019, T020, T010, T012, T004)
- [X] T022 [P] [US1] Extend `_build_match_record_summaries()` in `apps/api/app/domains/group/service.py` to select `RosterEntry.member_id` and populate `ParticipantSummary.member_id` (depends on T013, T003)
- [X] T023 [P] [US1] Extend the cross-group match-records builder in `apps/api/app/domains/member/service.py` the same way (depends on T014, T003)
- [X] T024 [P] [US1] Add `sendFriendRequestByMemberId(memberId)` and `getInviteCandidatesStatus(memberIds)` to `apps/web/src/app/features/friends/friends.service.ts` (depends on T007)
- [X] T025 [US1] Create `AddFriendButtonComponent` (`.ts`/`.html`/`.scss`) in `apps/web/src/app/shared/add-friend-button/` — input `memberId`, internally batches via a small per-page candidate store fed by `getInviteCandidatesStatus()`, three-state render, optimistic update on send (depends on T015, T024)
- [X] T026 [P] [US1] Wire `<app-add-friend-button>` into `match-history.component.html`/`.ts` — collect visible `member_id`s (excluding self), batch-query candidates, render per participant (depends on T016, T025, T022)
- [X] T027 [P] [US1] Wire `<app-add-friend-button>` into `group-member-view/match-records.component.html`/`.ts` the same way, including teammates (depends on T017, T025, T023)
- [X] T028 [P] [US1] Add `friends.addFromMatchButton` i18n key to `apps/web/src/assets/i18n/zh-TW.json` and `en.json` (existing `pendingOutgoing`/`pendingIncoming`/`alreadyFriends`/error-code keys are reused verbatim — no changes needed there)

**Checkpoint**: User Story 1 is fully functional and independently testable — "加好友" works from both match-records pages for Members, never for Guests or self.

---

## Phase 4: User Story 2 - 從即時戰況（進行中賽程）頁面直接發送好友邀請 (Priority: P2)

**Goal**: A logged-in member (or the group's admin, from the admin page's embedded court-control section) sees the same "加好友" entry next to a currently in-progress match's participants, without waiting for the match to finish.

**Independent Test**: With a match in progress between two non-friend members, click "加好友" next to the opponent from both the member-facing "賽程" page and the admin's court-control section; confirm a pending request is created either way; confirm the entry is absent from the "next up" queued-match preview; confirm that once the court advances to its next match, the entry updates to the new participants with no stale leftover; confirm the public, no-login scoreboard/control-panel pages and their Ably broadcast payload never carry `member_id` or any invite affordance.

### Tests for User Story 2

- [X] T029 [P] [US2] Unit test: `build_schedule_snapshot()`'s current-match query (`apps/api/app/domains/schedule/service.py`) populates `member_id` for `courts[].current_match.participants` (Member → id, Guest → `None`); `next_up.participants` stays without a populated `member_id` — extend `apps/api/tests/unit/domains/schedule/test_schedule_snapshot.py`
- [X] T030 [P] [US2] Regression test asserting `_match_participants_payload()`, `court_live_state()` (`GET /courts/by-token/{token}/state` response), and the `rotation.updated`/`score.updated` Ably payloads never contain a populated `member_id` — new test in `apps/api/tests/integration/test_schedule_lifecycle.py` or a new file, per research.md #1 and quickstart.md scenario 8
- [X] T031 [P] [US2] Regression test confirming `build_round_matches_list()`/`RoundMatchSummary` (admin's "本輪賽程清單") is unchanged — extend the existing round-matches-list test
- [X] T032 [P] [US2] Frontend test: `member-schedule.component` renders `<app-add-friend-button>` only for `courts[].current_match.participants`, never for `next_up.participants`, and never for Guest/self — `apps/web/src/app/features/group-member-view/member-schedule/member-schedule.component.spec.ts`
- [X] T033 [P] [US2] Frontend test: `group-admin/schedule-management/court-control.component` same behavior for the admin page — `court-control.component.spec.ts`
- [X] T034 [P] [US2] Frontend test: after a court's `current_match` changes (simulated schedule refresh), the rendered "加好友" entries update to the new participants with no leftover entry for the previous match's participants — extend `member-schedule.component.spec.ts` (FR-012)

### Implementation for User Story 2

- [X] T035 [US2] Extend `build_schedule_snapshot()`'s current-match query in `apps/api/app/domains/schedule/service.py` to select `RosterEntry.member_id` and populate `ParticipantSummary.member_id` — explicitly do **not** touch `_match_participants_payload()`/`court_live_state()`/`build_round_matches_list()` (depends on T029, T003)
- [X] T036 [P] [US2] Wire `<app-add-friend-button>` into `member-schedule.component.html`/`.ts` for `current_match.participants` only (depends on T032, T025, T035)
- [X] T037 [P] [US2] Wire `<app-add-friend-button>` into `group-admin/schedule-management/court-control.component.html`/`.ts` the same way (depends on T033, T025, T035)
- [X] T038 [US2] Ensure both components re-batch `getInviteCandidatesStatus()` for the new participant set whenever their existing Ably-driven schedule refresh replaces `current_match` (depends on T034, T036, T037)

**Checkpoint**: User Stories 1 AND 2 both independently functional; the public no-login scoreboard/control-panel surfaces are unaffected (T030).

---

## Phase 5: User Story 3 - 會員可關閉「被加好友」曝光，保護隱私 (Priority: P2)

**Goal**: A member can independently turn off "allow being added as a friend via match-record/live-status pages" in Privacy Settings; once off, the entry point disappears for anyone without an existing relationship, and the send endpoint itself rejects an attempt made from stale client state.

**Independent Test**: Turn the new toggle off for member E; confirm a non-friend viewer no longer sees any "加好友" entry for E anywhere; confirm an already-pending or already-accepted relationship involving E is unaffected; confirm a send attempt that races past a stale "eligible" UI state is rejected server-side with `INVITE_VIA_MATCH_PAGES_NOT_ALLOWED`.

### Tests for User Story 3

- [X] T039 [P] [US3] Unit test: `update_privacy_settings()` persists `allow_friend_invite_from_match_pages` and leaves the other two privacy fields untouched when omitted — extend `apps/api/tests/unit` coverage for `apps/api/app/domains/member/service.py`
- [X] T040 [P] [US3] Contract test: `PATCH /members/me/privacy-settings` reads/writes the new field; `GET /members/me` returns it; **and asserts the pre-`PATCH` default value is `true` for an unmodified member (FR-007)** — extend `apps/api/tests/contract/test_member_personal_settings.py`
- [X] T041 [P] [US3] Unit test: `create_friend_request_by_member_id()` raises `INVITE_VIA_MATCH_PAGES_NOT_ALLOWED` (403) when the target's toggle is off and no relationship exists yet; still returns `ALREADY_FRIENDS`/creates successfully regardless of the toggle once a relationship already exists (FR-009) — extend `test_create_friend_request_by_member_id.py`
- [X] T042 [P] [US3] Unit test: `get_invite_candidates_status()` returns `invite_eligible: false` when the target's toggle is off (and `friendship_status: "none"`); **and, when the toggle is off but a `friends`/`pending_outgoing`/`pending_incoming` relationship already exists, still reports that `friendship_status` correctly (FR-009 — toggle only affects the `none` case)** — extend `test_invite_candidates_status.py`
- [X] T043 [P] [US3] Frontend test: the settings privacy section renders the new toggle at its current value and persists a change via `PATCH /members/me/privacy-settings` — `apps/web/src/app/features/member/settings/settings.component.spec.ts`

### Implementation for User Story 3

- [X] T044 [US3] Add the `allow_friend_invite_from_match_pages` check (raising `INVITE_VIA_MATCH_PAGES_NOT_ALLOWED`) into `_create_friend_request_for_addressee()`'s member-id path in `apps/api/app/domains/friend/service.py`, applied only when no relationship already exists (depends on T041, T018/T019)
- [X] T045 [US3] Extend `update_privacy_settings()` in `apps/api/app/domains/member/service.py` to read/write the new field (depends on T039, T005)
- [X] T046 [US3] Wire the new field through `PATCH /members/me/privacy-settings` and `GET /members/me` in `apps/api/app/domains/member/router.py` (depends on T040, T045)
- [X] T047 [US3] Add the new toggle (label/hint/control) to `apps/web/src/app/features/member/settings/settings.component.ts`/`.html` under the existing 隱私設定 section, plus `settings.privacy.allowMatchPageInviteLabel`/`Hint` and `errors.INVITE_VIA_MATCH_PAGES_NOT_ALLOWED` i18n keys in `zh-TW.json`/`en.json` (depends on T043)

**Checkpoint**: All three stories independently functional; FR-006–010 fully enforced end-to-end (the toggle now actually changes send-endpoint behavior, not just the read-only `invite_eligible` hint).

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T048 [P] Run `specs/026-match-record-friend-invite/quickstart.md` end-to-end against the local Docker Compose stack (all 8 scenarios, including the FR-013/public-page regression check in scenario 8)
- [X] T049 Full regression pass: backend `ruff check` + `mypy --strict` + `pytest`; frontend `ng lint` + `ng build --configuration development` + `ng test --watch=false`

**Notes on requirements with no dedicated task**: FR-014 (existing page access permissions unchanged) and FR-015 (the entry point MUST NOT extend into the 016/023 single-match detail dialog) require no new code — no auth dependency is touched by any task above, and `MatchRecordDetailDialogComponent` is deliberately left unmodified; both are covered by the full regression pass (T049) and quickstart (T048) rather than a dedicated implementation task.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup (T001) — BLOCKS all three user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion. No dependency on US2/US3.
- **User Story 2 (Phase 4)**: Depends on Foundational completion. Reuses `AddFriendButtonComponent`/`FriendsService` methods built in US1 (T024/T025) — not independently buildable *before* US1, but independently *testable/deployable* once both exist, same relationship as 025's US1→US2.
- **User Story 3 (Phase 5)**: Depends on Foundational completion and on US1's `create_friend_request_by_member_id()`/`get_invite_candidates_status()` (T019/T020) existing to extend. Independently testable once those exist.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Parallel Opportunities

- Foundational: T003–T007 are all parallel (five different files).
- US1: T008–T017 (all ten test tasks) are parallel (different files/frameworks). T022/T023/T024 are parallel once their respective tests exist. T026/T027/T028 are parallel once T025 exists.
- US2: T029–T034 are parallel. T036/T037 are parallel once T035 exists.
- US3: T039–T043 are parallel.

---

## Parallel Example: User Story 1

```bash
# Tests, launched together:
Task: "create_friend_request() unchanged-behavior regression test"
Task: "create_friend_request_by_member_id() unit tests"
Task: "POST /friends/requests/by-member contract test"
Task: "get_invite_candidates_status() unit tests"
Task: "POST /friends/invite-candidates contract test"
Task: "group match-records member_id population test"
Task: "cross-group match-records member_id population test"
Task: "AddFriendButtonComponent three-state render test"
Task: "match-history.component wiring test"
Task: "group-member-view/match-records.component wiring test"

# Implementation, launched together once their tests exist:
Task: "_build_match_record_summaries() member_id — group/service.py"
Task: "cross-group builder member_id — member/service.py"
Task: "FriendsService new methods — friends.service.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1).
2. **STOP and VALIDATE**: run quickstart.md scenarios 1 and 2 — "加好友" works from both match-records pages, Guest/self correctly excluded.
3. This alone delivers the feature's core stated value (one-click invite from a page where you already recognize the other person) even before US2's live-schedule surfaces or US3's opt-out exist.

### Incremental Delivery

1. Setup + Foundational → shapes ready, no behavior change.
2. Add US1 → validate independently → match-records invite works end-to-end (MVP).
3. Add US2 → validate independently → live-schedule/admin-page surfaces added, public pages confirmed unaffected.
4. Add US3 → validate independently → opt-out toggle now actually blocks new invites.
5. Polish → full regression + quickstart replay (all 8 scenarios).

---

## Notes

- [P] tasks touch different files with no unmet dependency.
- Tests are written before their corresponding implementation task; each task is done only when its test(s) pass and the full suite (backend + frontend) stays green.
- research.md #1 is the load-bearing constraint across US1/US2: `member_id` is added to a type shared by 8+ call sites, three of which (T022/T023/T035) are safe to populate and three of which (`_match_participants_payload()`/`court_live_state()`/`build_round_matches_list()`) are explicitly never touched — T030/T031 exist specifically to prove that boundary holds.
- Avoid: adding `member_id` reads/writes to any function other than the three named in T022/T023/T035; adding the `AddFriendButtonComponent` anywhere the participant's `member_id` might be `null` without the existing Guest/self guard.
