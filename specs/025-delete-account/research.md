# Phase 0 Research: 刪除帳號

## 1. Anonymize in place vs. hard-delete the `Member` row

**Decision**: Anonymize in place (overwrite fields, keep the row and its
`id`). Already settled by the spec (US2/FR-006), confirmed against the
codebase: `members.id` is referenced by `FOREIGN KEY` from `groups.
created_by_member_id`, `friend_requests.requester_id`/`addressee_id`,
`group_invites.inviter_id`/`invitee_id`, `roster_entries.member_id`,
`notifications.member_id` (this last one `ON DELETE CASCADE` — meaning a
hard delete would silently wipe the deleted member's own notification
inbox, which is moot since they can no longer log in to see it anyway, but
confirms hard-delete was never actually viable without a cascade audit of
every one of these tables first).

**Alternatives considered**: Hard delete with `ON DELETE SET NULL`/cascade
tuning across 5 tables — rejected: `roster_entries.nickname` and match
participant rows would need special-case handling regardless (they're not
FK-nullable-away without losing the match record itself), so hard-delete
buys nothing but risk for this feature's actual goal.

## 2. How is the account made unable to log in, immediately, everywhere?

**Decision**: Three fields change, no new invalidation mechanism needed:
- `password_hash` is overwritten with the hash of a random, discarded
  value (`hash_password(secrets.token_urlsafe(32))`) — even if the
  placeholder email were somehow guessed, no password ever verifies
  against it.
- `email` is overwritten with a synthetic, per-member-unique placeholder
  (`f"deleted-{member.id}@rally-stats.invalid"`). `login()` looks up by
  `Member.email == email.lower()` — once the real email no longer matches
  any row, `login()` naturally returns `INVALID_CREDENTIALS` for it
  (confirmed by reading `service.py`'s `login()`), with no separate
  "is this account deleted" check needed in the login path at all.
- `token_version` is incremented, exactly like `change_password()`/
  `reset_password()` already do. Confirmed in `security.py`:
  `_load_member_for_token()` re-reads the member row on **every** request
  and rejects if `member.token_version != payload["token_version"]` — so
  this one field bump immediately invalidates every existing access/
  refresh token on any device, the moment the deletion transaction commits
  (satisfies FR-004's "any device already logged in" clause with the exact
  mechanism this codebase already uses for the same purpose elsewhere).

**Alternatives considered**: A separate token/session blocklist — rejected,
`token_version` already does this codebase-wide; adding a second mechanism
for one feature would violate Constitution VI (Modularity/no parallel
logic).

## 3. Where does "is this account deleted" need to be checked going forward?

**Decision**: Add `members.deleted_at` (nullable timestamp, `NULL` = active)
as the single source of truth for "is this a live, usable account" — used
to gate **new** actions on a deleted member, never to gate **viewing
already-existing** data about them (that distinction is exactly what
separates FR-006/US2 from the Edge Cases below):

- `search_member()` (`member/service.py`): add `or target.deleted_at is not
  None` to the existing `MEMBER_NOT_FOUND` condition — reuses the same
  error code already used for "unverified" and "not searchable", keeping
  a deleted account indistinguishable from "doesn't exist" (same
  non-disclosure principle the existing check already follows).
- `create_friend_request()` (`friend/service.py`): same addition to its
  existing `addressee.verification_status != "verified"` → `MEMBER_NOT_FOUND`
  check.
- `send_invite()` (`group_invite/service.py`): same addition for the
  invitee lookup.
- `list_invitable_friends()` (`group_invite/service.py`): filter out
  friends with `deleted_at is not None` from the invitable list (a friend
  who no longer has a usable account can't accept an invite).

**Explicitly NOT gated by `deleted_at`**: `_resolve_viewable_member()`
(023's friend-match-record viewing) and every match-history/roster/
standings read path — these must keep working per US2, and already do
without any change, because they never check `deleted_at` at all; they
only ever checked `verification_status`, which deletion deliberately does
not touch (see #5).

## 4. Cascading the historical nickname (FR-003a)

**Decision**: One `UPDATE roster_entries SET nickname = :placeholder WHERE
member_id = :member_id` in the same transaction as the `Member` row update
— covers every roster entry regardless of match/round status (queued,
in-progress, completed), satisfying the Edge Case that a currently
in-progress match's live scoreboard must also show the placeholder, not
just historical ones.

This is a **deliberate, narrowly-scoped exception** to the existing
"changing your nickname MUST NOT cascade to `roster_entries`" precedent
(`006-member-friends`, enforced by `test_nickname_snapshot_isolation.py`).
That test and its underlying `set_nickname()` service function are
untouched by this feature — the cascade lives entirely inside the new
`delete_account()` function, which is the only code path allowed to write
to `roster_entries.nickname` for a reason other than the member joining a
new roster.

## 5. Placeholder text: one fixed literal, not routed through i18n

**Decision**: A single fixed placeholder string, `"Deleted User"`, used for
both `Member.nickname` and the `RosterEntry.nickname` cascade — a plain
Python/TypeScript constant, not an `ngx-translate` key.

**Rationale**: Nicknames are user-generated **data**, not UI chrome — a
Chinese-named player's nickname already doesn't change when a viewer
switches the app's display language (024's i18n work never touched
nicknames, by design). The placeholder is exactly the same kind of value:
data, not UI text. Treating it as a translation key would be the first
exception to that existing rule, and would require touching every one of
the ~20 templates across the frontend that interpolate `.nickname` directly
(`match-records`, `standings`, `scoreboard`, `control-panel`, `schedule-
management/*`, `friend-list`, etc. — enumerated via `grep -rl "\.nickname"`)
to route through a new pipe — a large, feature-disproportionate refactor
for a cosmetic-only gain (an English-reading user seeing "Deleted User" in
an otherwise-Chinese nickname slot is no more confusing than seeing any
other member's literal nickname in a script they don't read, which already
happens today).

**Alternatives considered**:
- A sentinel value + shared Angular pipe that all nickname-display
  templates adopt, translating it via a new `common.deletedUser` i18n key:
  rejected as disproportionate scope for this feature (see above) — worth
  reconsidering only if a future feature needs a *general* nickname-
  rendering abstraction for other reasons.
- Bilingual literal like "已刪除的使用者 / Deleted User" crammed into one
  string: rejected — `nickname` columns are `String(20)`, no room, and it
  would look broken wherever nicknames render inline with scores (e.g. the
  scoreboard's large-font team display).

## 6. Endpoint shape

**Decision**: `POST /members/me/delete`, body `{ current_password: string
}`, auth via `require_member` (not `require_verified_member` — an
unverified member can still delete their own account, per Edge Cases),
response `{ deleted: true }` (same boolean-ack shape as `ResetPasswordResponse`/
`ChangePasswordResponse`). Reuses the existing `CURRENT_PASSWORD_INCORRECT`
error code — no new error code needed.

**Alternatives considered**: `DELETE /members/me` — rejected: the frontend's
shared `ApiClient.delete<T>(path, headers)` helper has no body parameter
today (checked `api-client.ts`), and DELETE-with-a-body is inconsistent
support across HTTP infra; every other *action* endpoint in this codebase
that isn't a pure resource removal already uses POST with a body (`POST
/auth/reset-password/{token}`, `POST /auth/resend-verification`), so `POST
/members/me/delete` matches existing convention rather than introducing a
new one.
