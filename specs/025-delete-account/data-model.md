# Phase 1 Data Model: 刪除帳號

## Schema change

### `members.deleted_at` (new column)

- `TIMESTAMPTZ NULL`, default `NULL`.
- `NULL` = active, usable account (all existing rows, unaffected).
- Non-`NULL` = this account has been deleted; the timestamp is informational
  only (not read by any business logic beyond "is it set").
- One Alembic migration, purely additive — no backfill needed since every
  existing row correctly defaults to `NULL`.

## Fields overwritten by `delete_account()` (no schema change, value change only)

| Field | Table | Before | After |
|---|---|---|---|
| `email` | `members` | real address | `deleted-{member_id}@rally-stats.invalid` |
| `password_hash` | `members` | real hash | hash of a random, discarded value |
| `nickname` | `members` | real nickname (or `NULL`) | `"Deleted User"` |
| `deleted_at` | `members` | `NULL` | now() |
| `token_version` | `members` | N | N+1 |
| `nickname` | `roster_entries` (every row where `member_id` = this member) | whatever was captured at join time | `"Deleted User"` |
| `used_at` | `email_verification_tokens` (every unused row for this member) | `NULL` | now() |
| `used_at` | `password_reset_tokens` (every unused row for this member) | `NULL` | now() |

Fields deliberately **left untouched**: `verification_status` (stays
whatever it was — this is what keeps `_resolve_viewable_member()` and
friend-match-record viewing working for US2, since that check only ever
looked at `verification_status`, never `deleted_at`), `user_number`,
`created_at`, `allow_search`/`share_match_records_with_friends` (moot once
`deleted_at` gates search/friend-request directly), `language_preference`.

## Existing relationships (unaffected — this is the whole point of
anonymizing instead of deleting the row)

- `groups.created_by_member_id` → `members.id`
- `friend_requests.requester_id` / `addressee_id` → `members.id`
- `group_invites.inviter_id` / `invitee_id` → `members.id`
- `roster_entries.member_id` → `members.id` (nullable — guest entries
  already have `NULL` here; unaffected)
- `notifications.member_id` → `members.id` (`ON DELETE CASCADE` — moot
  since the row is never actually deleted)
- `member_login_records.member_id`, `email_verification_tokens.member_id`,
  `password_reset_tokens.member_id` → `members.id` (`ON DELETE CASCADE` —
  same, moot)

None of these require any migration or model change — they continue
pointing at the same (now-anonymized) `Member` row exactly as before.
