# Quickstart: 刪除帳號

Validation scenarios mirroring spec.md's acceptance scenarios. Run against
local Docker Compose (`cd infra && docker compose up -d --build web api`).

## Prerequisites

- Two test member accounts, A and B, both verified, both members of at
  least one shared group with at least one completed match between them
  (so B has something to view of A's history after A deletes their
  account).

## Scenario 1 — Deletion itself (US1)

1. Log in as A. Go to 個人設定 → 安全性 (or wherever the danger-zone form
   lands). Enter A's current password and confirm deletion.
2. **Expected**: success response; A is redirected to a logged-out view.
3. Try logging in again as A with the original email/password.
   **Expected**: `INVALID_CREDENTIALS` (SC-001).
4. If A had another browser/device still logged in before step 1, confirm
   any action there now fails with `MEMBER_TOKEN_INVALID`.
5. If A had an unused verification or password-reset email link, confirm
   using it now fails (invalid/expired).

## Scenario 2 — Cancel leaves the account untouched

1. Log in as a fresh test member, start the delete flow, but enter the
   wrong password (or cancel before submitting).
2. **Expected**: account is unaffected — same email/password still log in
   normally afterward.

## Scenario 3 — Other members' history stays intact (US2)

1. As B (who played A in a completed match, per Prerequisites), view that
   match's record after A has deleted their account (Scenario 1).
2. **Expected**: the match record renders normally; A's name in that
   record shows "Deleted User", not A's real nickname, and not an error or
   blank field (SC-002).
3. If A had created a group B is still in, view that group.
   **Expected**: the group still functions — courts, schedule, other
   members unaffected.

## Scenario 4 — In-progress match at time of deletion (Edge Case)

1. Start a match with A as an active participant, keep it in progress
   (don't end it).
2. While it's in progress, delete A's account (as A, in a separate
   session/tab).
3. **Expected**: the live scoreboard/control panel for that in-progress
   match now shows "Deleted User" for A, without needing the match to end
   first.

## Scenario 5 — Deleted accounts are unsearchable and un-friendable going forward

1. As B, search for A by A's (former) user number.
2. **Expected**: `MEMBER_NOT_FOUND` (indistinguishable from a account that
   never existed).
3. As B, attempt to send A a new friend request or invite A to a group
   (assuming B somehow still has A's user number/link).
   **Expected**: `MEMBER_NOT_FOUND`.
4. If B and A were already friends before A's deletion, confirm B's
   existing friend list still shows the historical friendship entry
   (labeled "Deleted User"), rather than silently disappearing.

## Scenario 6 — Freed email can be reused

1. Register a brand-new account using A's original (pre-deletion) email
   address.
2. **Expected**: registration succeeds — the email is no longer considered
   taken.

## Regression checks

- Existing members who never delete their account see zero change.
- Full test suites green: backend `pytest` + `ruff check` + `mypy --strict`;
  frontend `ng lint` + `ng build --configuration development` +
  `ng test --watch=false`.
- `test_nickname_snapshot_isolation.py` (006) still passes unchanged —
  confirms the *ordinary* nickname-change path still does NOT cascade to
  `roster_entries`, only account deletion does.
