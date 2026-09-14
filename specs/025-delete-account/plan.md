# Implementation Plan: 刪除帳號

**Branch**: `main` | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/025-delete-account/spec.md`

## Summary

A logged-in member can permanently delete their own account from 個人設定. Deletion is implemented as **anonymization, not a row delete**: the `Member` row survives (so every foreign key pointing at it — match participants, roster entries, friend requests, group creators — stays valid), but its identifying fields (email, password hash, nickname) are overwritten with non-identifying placeholder values, a new `deleted_at` timestamp marks it as gone, and `token_version` is bumped to immediately invalidate every existing session. Per the clarified scope, the member's historical `RosterEntry.nickname` snapshots (used throughout match/roster/scoreboard displays, and deliberately isolated from `Member.nickname` by an existing 006 precedent) are cascade-overwritten too, including any roster entry for a match still in progress. Confirmation requires re-entering the current password, mirroring the existing `change_password` flow.

## Technical Context

**Language/Version**: Python 3.12 / FastAPI (backend, `apps/api`); TypeScript 5 / Angular 20 (frontend, `apps/web`)

**Primary Dependencies**: SQLAlchemy 2.0 + asyncpg + Alembic (one migration: new `members.deleted_at` column); existing `passlib` password hashing; existing JWT `token_version` invalidation mechanism (`app/domains/member/security.py`)

**Storage**: PostgreSQL. One migration adds `members.deleted_at TIMESTAMPTZ NULL` (NULL = active account). No other schema change — `RosterEntry.nickname`, `Member.email`/`password_hash`/`nickname` are all overwritten in place, not restructured.

**Testing**: `pytest` (backend unit/contract), Angular `ng test` (Vitest)

**Target Platform**: Existing web app, Docker Compose local dev

**Project Type**: Web application (existing monorepo layout, no new top-level structure)

**Performance Goals**: SC-003 — the whole delete flow (confirm → done) completes in under 1 minute; the deletion itself is a single-transaction DB write, no batch job or async processing needed even for a member with a long match history (an `UPDATE ... WHERE member_id = :id` on `roster_entries` is one statement regardless of row count).

**Constraints**: FR-004 — deletion must take effect immediately, no grace period (confirmed in spec Assumptions: anonymization itself satisfies the legal "reasonable period" requirement, no separate retention window to build). FR-003a — the historical-nickname cascade is a **deliberate, deletion-only** exception to the existing "nickname changes MUST NOT cascade to `roster_entries`" precedent (`test_nickname_snapshot_isolation.py`, 006) — the plan must not weaken that existing precedent for the *ordinary* nickname-change path.

**Scale/Scope**: One backend endpoint, one new DB column, no new tables. Frontend: one new form in an existing page (個人設定), reusing existing patterns (password re-entry, danger-zone styling already established by `adminPage.dangerZoneSectionTitle`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Code Quality & Type Safety** — PASS. Straightforward typed service function and Angular form, no `any`.
- **II. Test-First** — N/A scope (account deletion isn't group/roster/scoring core logic per the principle's own stated scope), but this session's convention of tests alongside implementation still applies and will be followed.
- **III. Real-Time Sync & Consistency** — N/A. No realtime/Ably surface touched.
- **IV. Authorization & Security** — Directly this feature's subject. PASS: deletion requires a valid Bearer token (`require_member` — not `require_verified_member`, per Edge Case: an unverified member can still delete) *and* the current password re-entered; password hash is one-way (unchanged); the placeholder email/password-hash are never derived from anything guessable. Existing unused verification/reset tokens are explicitly invalidated (FR-005).
- **V. UX Confirmation for Destructive Actions** — PASS, and exceeds the baseline: the constitution requires "a clear confirmation flow" for destructive actions (disband group, kick member, etc. use a plain confirm dialog); this feature's Assumption deliberately goes further (password re-entry) since account deletion is irreversible and crosses a security boundary, not just a data-loss boundary.
- **VI. Modularity** — PASS. One service function (`delete_account`) in the existing `member` domain; no new domain. The nickname-placeholder value is defined once and reused for both `Member.nickname` and the `RosterEntry.nickname` cascade.
- **VII. Accessibility & Mobile-First** — PASS. Danger-zone section follows the same `.btn--danger` + confirmation pattern already used elsewhere (admin page), which already meets touch-target/contrast requirements.
- **VIII. i18n & Timezone Architecture** — The placeholder nickname text is a **data value**, not UI chrome — like every other nickname in the system, it was never part of the translation-file system (a nickname doesn't change when the viewer switches language today, and this feature doesn't change that). It is intentionally a fixed, language-neutral literal ("Deleted User") rather than routed through `ngx-translate`, for the same reason existing nicknames aren't. The *labels around it* (button text, confirmation copy, error messages) do go through the existing i18n system as usual (`errors.CURRENT_PASSWORD_INCORRECT` is reused, no new error code).
- **IX. Portability & Deployability** — PASS. One additive, backward-compatible migration (nullable column, no data migration needed for existing rows — they default to `NULL` = not deleted).
- **X. Server as Source of Truth** — PASS. `deleted_at` and the token-invalidating `token_version` bump are both server-side; the frontend never locally guesses whether an account is deleted.
- **XI. Anti-Bot & Abuse Prevention** — N/A. Not a resource-creation endpoint; it's a self-service action on the caller's own authenticated account, gated by their own password.

No unjustified violations. Proceeding to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/025-delete-account/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── delete-account-api.md   # Phase 1 output
└── tasks.md               # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/
│   └── <new>_member_deleted_at.py     # add members.deleted_at (nullable)
└── app/domains/
    ├── member/
    │   ├── models.py       # Member.deleted_at
    │   ├── schemas.py      # DeleteAccountRequest/Response
    │   ├── router.py       # POST /members/me/delete
    │   └── service.py      # delete_account(); deleted_at guard added to
    │                       # search_member() (reuses MEMBER_NOT_FOUND)
    ├── friend/service.py   # deleted_at guard added to create_friend_request()
    │                       # (reuses MEMBER_NOT_FOUND)
    └── group_invite/service.py  # deleted_at guard added to send_invite()
                                  # and/or list_invitable_friends() filters
                                  # out deleted friends (research.md #4)

apps/web/src/
└── app/
    ├── core/api/member-auth.models.ts      # DeleteAccountRequest/Response
    └── features/
        ├── auth/auth.service.ts             # deleteAccount()
        └── member/settings/
            ├── settings.component.ts        # danger-zone form + submit
            ├── settings.component.html
            └── settings.component.scss
```

No new top-level module — this extends the existing `member`/`friend`/`group_invite` domains and the existing 個人設定 page.
