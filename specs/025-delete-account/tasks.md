---
description: "Task list for 025-delete-account"
---

# Tasks: 刪除帳號

**Input**: Design documents from `/specs/025-delete-account/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/delete-account-api.md, quickstart.md

**Tests**: Included — this session's established convention is tests alongside/before each implementation task, run to full-suite green before a task is considered done. (Constitution II's Test-First mandate itself doesn't apply — its scope is group/roster/scoring core logic, not account management.)

**Organization**: Tasks are grouped by user story (US1 = P1, US2 = P2) per spec.md priorities.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 or US2
- Paths are exact, relative to repo root

---

## Phase 1: Setup

**Purpose**: The one schema change everything else depends on.

- [X] T001 Create an Alembic migration adding `members.deleted_at` (`TIMESTAMPTZ NULL`, default `NULL`) in `apps/api/alembic/versions/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Model/schema plumbing both user stories build on. No behavior change yet.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Add `deleted_at: Mapped[datetime | None]` to `Member` in `apps/api/app/domains/member/models.py` (depends on T001)
- [X] T003 [P] Add `DeleteAccountRequest` (`current_password: str`) and `DeleteAccountResponse` (`deleted: bool`) to `apps/api/app/domains/member/schemas.py`
- [X] T004 [P] Add `DeleteAccountRequest`/`DeleteAccountResponse` TypeScript interfaces to `apps/web/src/app/core/api/member-auth.models.ts`

**Checkpoint**: Schema and shape definitions exist; nothing yet reads or writes `deleted_at`.

---

## Phase 3: User Story 1 - 會員刪除自己的帳號 (Priority: P1) 🎯 MVP

**Goal**: A logged-in member can delete their own account (password re-entry required); the account is immediately unusable everywhere (login, existing sessions, unused email/reset tokens) and drops out of search/friend-request/group-invite going forward.

**Independent Test**: Delete a test account, confirm it can no longer log in with the original credentials, confirm another still-logged-in session for that account now fails, confirm the freed email can be used to register a new account, confirm the deleted account is unsearchable and un-friendable.

### Tests for User Story 1

- [X] T005 [P] [US1] Unit tests for `delete_account()` in new file `apps/api/tests/unit/domains/member/test_delete_account.py`: wrong password → `CURRENT_PASSWORD_INCORRECT`, account fields unchanged; correct password → `email`/`password_hash`/`nickname` overwritten, `deleted_at` set, `token_version` incremented; every `roster_entries.nickname` row for this member overwritten regardless of match/round status (queued/in_progress/completed); every *unused* verification/reset token for this member marked used; an *already-used* token is left untouched
- [X] T006 [P] [US1] Contract test for `POST /members/me/delete` in new file `apps/api/tests/contract/test_delete_account.py`: 200 + `{"deleted": true}` on success; 400 `CURRENT_PASSWORD_INCORRECT` on wrong password; 401 with no/invalid auth; succeeds for an *unverified* member (no `EMAIL_NOT_VERIFIED` gate)
- [X] T007 [P] [US1] Contract/unit tests: after deletion, `POST /auth/login` with the original email/password returns `INVALID_CREDENTIALS`; a previously-issued access token for that member now returns `MEMBER_TOKEN_INVALID`; a new `POST /auth/register` using the original (now-freed) email succeeds — in `apps/api/tests/contract/test_delete_account.py`
- [X] T008 [P] [US1] Tests: `search_member()` and `create_friend_request()` return `MEMBER_NOT_FOUND` for a deleted target/addressee, added as siblings of the existing `test_search_excludes_unverified_account`/`test_create_friend_request_excludes_unverified_account` in `apps/api/tests/unit/domains/friend/test_search_exclusions.py`; `send_invite()` returns `MEMBER_NOT_FOUND` for a deleted invitee in `apps/api/tests/unit/domains/group_invite/test_send_invite.py`; `list_invitable_friends()` excludes a deleted friend in `apps/api/tests/unit/domains/group_invite/test_list_invitable_friends.py`
- [X] T009 [P] [US1] Frontend test: `AuthService.deleteAccount()` calls `POST /members/me/delete` with `{ current_password }` in `apps/web/src/app/features/auth/auth.service.spec.ts`
- [X] T010 [P] [US1] Frontend test: settings danger-zone form shows the `errors.CURRENT_PASSWORD_INCORRECT` key inline on failure, and on success calls `AuthService.logout()` and navigates away from the member area, in `apps/web/src/app/features/member/settings/settings.component.spec.ts`

### Implementation for User Story 1

- [X] T011 [US1] Implement `delete_account(session, member, current_password)` in `apps/api/app/domains/member/service.py`: verify password; overwrite `email`/`password_hash`/`nickname`; set `deleted_at`; increment `token_version`; `UPDATE roster_entries SET nickname = <placeholder> WHERE member_id = :id`; mark unused `EmailVerificationToken`/`PasswordResetToken` rows used; single transaction (depends on T005)
- [X] T012 [US1] Add `POST /members/me/delete` in `apps/api/app/domains/member/router.py`, `require_member` (not `require_verified_member`), calling `service.delete_account()` (depends on T006, T007, T011)
- [X] T013 [US1] Add `or target.deleted_at is not None` to `search_member()`'s existing `MEMBER_NOT_FOUND` condition in `apps/api/app/domains/member/service.py` (depends on T008)
- [X] T014 [US1] Add the same `deleted_at` condition to `create_friend_request()`'s addressee check in `apps/api/app/domains/friend/service.py` (depends on T008)
- [X] T015 [US1] Add the same `deleted_at` condition to `send_invite()`'s invitee check, and filter deleted friends out of `list_invitable_friends()`'s result, both in `apps/api/app/domains/group_invite/service.py` (depends on T008)
- [X] T016 [US1] Add `deleteAccount(currentPassword: string): Observable<DeleteAccountResponse>` to `apps/web/src/app/features/auth/auth.service.ts` (depends on T009)
- [X] T017 [US1] Add a danger-zone delete-account form (password field, confirm button) to `apps/web/src/app/features/member/settings/settings.component.ts` + `.html` + `.scss` (under the 安全性 tab) — on success, call `AuthService.logout()` and navigate to `/` (depends on T010, T016)
- [X] T018 [US1] Add the danger-zone i18n keys (section title, hint, password field label, confirm button, success/redirect copy) to `apps/web/src/assets/i18n/zh-TW.json` and `apps/web/src/assets/i18n/en.json`

**Checkpoint**: User Story 1 is fully functional and independently testable — an account can be deleted, is immediately unusable, and disappears from future search/friend/invite flows.

---

## Phase 4: User Story 2 - 其他會員查看的既有紀錄不因對方刪除帳號而毀損 (Priority: P2)

**Goal**: Confirm that everything else in the app that reads a deleted member's historical data — match records, roster/standings, groups they created — keeps working exactly as before, showing "Deleted User" instead of erroring or going blank.

**Independent Test**: Seed a completed match and a group between two members, delete one of them, then confirm the other member's views of that shared history render correctly with the placeholder name.

**No new implementation for this story** — by design (research.md #1/#3, data-model.md), anonymization deliberately leaves `verification_status` and every read path untouched; US1's `delete_account()` (T011) and the `roster_entries` cascade already are the entire mechanism. This phase is test/verification-only.

### Tests for User Story 2

- [X] T019 [P] [US2] Integration test: seed a completed match between member A and member B, delete A, then confirm `view_member_match_records()`/`get_member_match_record_detail()` (called as B, viewing A) still return the match with A's participant nickname as "Deleted User" — in `apps/api/tests/integration/test_delete_account_history_preserved.py` (new file)
- [X] T020 [P] [US2] Integration test: seed a group created by member A (`is_creator` roster entry), delete A, then confirm the group's schedule/roster/standings endpoints still function normally for other members — same new file as T019
- [X] T021 [P] [US2] Regression test: run `apps/api/tests/unit/domains/member/test_nickname_snapshot_isolation.py` (006) unchanged and confirm it still passes — the *ordinary* nickname-change path must still NOT cascade to `roster_entries`, only account deletion does

**Checkpoint**: User Stories 1 AND 2 both verified — deletion works, and nothing else in the app breaks because of it.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T022 [P] Run `specs/025-delete-account/quickstart.md` end-to-end against the local Docker Compose stack (all 6 scenarios + regression checks)
- [X] T023 Full regression pass: backend `ruff check` + `mypy --strict` + `pytest` (confirm 861+ existing tests plus all new ones pass, including T021's unchanged isolation test); frontend `ng lint` + `ng build --configuration development` + `ng test --watch=false`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup (T001) — BLOCKS both user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion. No dependency on US2.
- **User Story 2 (Phase 4)**: Depends on User Story 1 being implemented (T011's cascade is literally what T019/T020 verify) — unlike most features in this repo, US2 here is not independently implementable before US1, only independently *testable* as its own checkpoint once US1 exists.
- **Polish (Phase 5)**: Depends on both user stories being complete.

### Parallel Opportunities

- Foundational: T003 and T004 are parallel (backend schema vs. frontend model file).
- US1: T005–T010 (all six test tasks) are parallel (different files/frameworks). T013/T014/T015 touch three different domain files and are parallel once T008's tests exist.
- US2: T019, T020, T021 are parallel (T019/T020 share one new file but cover independent scenarios within it — write them as separate test functions in the same file, not a merge conflict; T021 is a separate existing file).

---

## Parallel Example: User Story 1

```bash
# Tests, launched together:
Task: "delete_account() unit tests — test_delete_account.py (unit)"
Task: "POST /members/me/delete contract tests — test_delete_account.py (contract)"
Task: "login/token/re-registration tests after deletion — test_delete_account.py (contract)"
Task: "deleted_at guard tests — search/friend-request/invite"
Task: "AuthService.deleteAccount() test — auth.service.spec.ts"
Task: "settings danger-zone form test — settings.component.spec.ts"

# Guard additions, launched together once T008's tests exist:
Task: "search_member() deleted_at guard — member/service.py"
Task: "create_friend_request() deleted_at guard — friend/service.py"
Task: "send_invite()/list_invitable_friends() deleted_at guard — group_invite/service.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1).
2. **STOP and VALIDATE**: run quickstart.md Scenarios 1, 2, 5, 6 — deletion itself, cancel-leaves-untouched, unsearchable/un-friendable, freed email.
3. This alone delivers the feature's entire stated purpose (a member can exercise their deletion right) even before US2's verification pass.

### Incremental Delivery

1. Setup + Foundational → schema ready, no behavior change.
2. Add US1 → validate independently → deletion works end-to-end (MVP).
3. Add US2 → validate independently → confirms nothing else broke (no new code, verification only).
4. Polish → full regression + quickstart replay.

---

## Notes

- [P] tasks touch different files with no unmet dependency.
- Tests are written before their corresponding implementation task; each task is done only when its test(s) pass and the full suite (backend + frontend) stays green.
- T011's `roster_entries` cascade is a deliberate, deletion-only exception to the existing nickname-snapshot-isolation precedent (research.md #4) — T021 exists specifically to prove that exception didn't leak into the ordinary nickname-change path.
- Avoid: touching `set_nickname()` or `test_nickname_snapshot_isolation.py`'s existing assertions — only `delete_account()` is allowed to write to `roster_entries.nickname` for a reason other than joining a new roster.
