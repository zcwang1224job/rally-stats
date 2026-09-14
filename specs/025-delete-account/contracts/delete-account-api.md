# Contract: Account deletion API

## `POST /members/me/delete` (new)

- **Auth**: `require_member` (Bearer access token) — deliberately not
  `require_verified_member`; an unverified member can still delete their
  own account (Edge Cases).
- **Request body**:
  ```json
  { "current_password": "..." }
  ```
- **Response 200** — `DeleteAccountResponse`:
  ```json
  { "deleted": true }
  ```
- **Errors**:
  - `MEMBER_TOKEN_INVALID` (401) — via `require_member`, standard.
  - `CURRENT_PASSWORD_INCORRECT` (400) — reused from `change_password`,
    wrong password re-entry. Account is untouched.
- **Side effects** (all in one transaction, all-or-nothing):
  - `Member.email`, `Member.password_hash`, `Member.nickname` overwritten
    with placeholders; `Member.deleted_at` set; `Member.token_version`
    incremented (see data-model.md).
  - Every `RosterEntry.nickname` row for this member overwritten with the
    same placeholder (FR-003a).
  - Every unused `EmailVerificationToken`/`PasswordResetToken` for this
    member marked used (FR-005).
- **Client behavior after success**: the access/refresh tokens the client
  was holding are now invalid (same as any other `token_version` bump) —
  the frontend clears local auth state and redirects to a logged-out view,
  exactly as `logout()` already does; no new client-side session-clearing
  logic needed beyond calling the existing `AuthService.logout()` after a
  successful response.

## Existing endpoints, behavior change (no shape change)

### `GET /members/search` (`search_member()`)

A deleted account now also returns `MEMBER_NOT_FOUND` (404) — same code
already used for "doesn't exist," "unverified," and "has search turned
off." No response shape change; purely an additional condition folded into
the existing check.

### `POST /friends` (`create_friend_request()`)

A deleted addressee now also returns `MEMBER_NOT_FOUND` (404) — same
addition as above.

### `POST /groups/{group_id}/invites` (`send_invite()`)

A deleted invitee now also returns `MEMBER_NOT_FOUND` (404) — same
addition.

### `GET /groups/{group_id}/invitable-friends` (`list_invitable_friends()`)

A friend whose account has since been deleted is silently excluded from
the list (not an error — this list already excludes non-invitable friends
for other reasons, e.g. already a member).

## Unaffected existing endpoints (explicitly verified, not just assumed)

`GET /members/{member_id}/match-records[/{match_id}]` (023, friend match-
record viewing), all group/roster/scoreboard read endpoints — none of
these check `deleted_at`; they continue to work for a deleted member's
historical data exactly as before, per US2.
