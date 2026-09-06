# Reused API Contracts

**Feature**: [../spec.md](../spec.md)

This feature (User Story 7) implements the backend endpoints below for the
first time, but does **not** define their request/response shapes,
authorization rules, or error codes — those are already fully specified by
`specs/006-member-friends/`. This feature's job is limited to writing the
`service.py`/`router.py` code that fulfills the contracts exactly as
written there, plus building the frontend against them.

| Endpoint | Authoritative contract |
|---|---|
| `GET /members/search?user_number=` | `specs/006-member-friends/contracts/member-api.md` |
| `GET /members/me/groups` | `specs/006-member-friends/contracts/member-api.md` |
| `GET /friends`, `POST /friends/requests`, `GET /friends/requests/incoming`, `POST /friends/requests/{id}/accept`, `POST /friends/requests/{id}/reject`, `DELETE /friends/{id}` | `specs/006-member-friends/contracts/friends-api.md` |
| `POST /groups/{group_id}/forgot-admin-pin` | `specs/006-member-friends/contracts/forgot-admin-pin-api.md` |

Any implementation task under User Story 7 (see tasks.md) MUST treat the
files above as the source of truth for request/response bodies, status
codes, and error codes — not this feature's own spec.md, which intentionally
does not restate them (see spec.md FR-018).

**One discovered gap, fixed during implementation**: 006's own `FriendSummary`
shape (used by `GET /friends`) omitted `friend_request_id`, but the
`DELETE /friends/{friend_request_id}` unfriend action it also defines has no
other way to learn which row to target from that list response. Added
`friend_request_id: str | None` to `FriendSummary` (populated in
`list_friends()`, left `None` when the same schema is reused inside
`IncomingFriendRequest`, whose own top-level field already covers that
case) — an additive fix, not a contract redesign.

All other endpoints this feature's UI reads from (schedule, court state,
group admin view, group list, scoreboard live state, etc.) are unchanged —
User Stories 1-6 are presentation-only and introduce no new endpoints or
response fields.
