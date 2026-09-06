# Phase 1 Data Model: 全站介面重新設計

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

## Reused entities (no changes)

This feature introduces **zero new database tables and zero schema
migrations**. All data entities needed by User Story 7 already exist,
already match their governing spec exactly, and are already migrated into
the running database:

| Entity | Defined in | Status |
|---|---|---|
| `members` (incl. `user_number`, `verification_status`, `token_version`) | `specs/006-member-friends/data-model.md` §1 | Migrated, in use (register/login/settings already work) |
| `email_verification_tokens`, `password_reset_tokens` | `specs/006-member-friends/data-model.md` §2-3 | Migrated, in use |
| `friend_requests` (state machine: `pending → accepted\|rejected`, `accepted → unfriended`) | `specs/006-member-friends/data-model.md` §4 | Migrated (`ebde39e08b3a_member_auth_and_friend_tables.py`), **not yet read/written by any endpoint** — this feature adds the service/router code that operates on it |
| `groups` (`created_by_member_id`, `admin_pin_hash`, `admin_token_version`) | `specs/architecture.md` / 001 | Existing, reused as-is by `forgot-admin-pin` (same fields `regenerate-admin-pin` already updates) |

US1-US6 (scoreboard, control panel, admin page, home, join flow, member
pages) read and display **existing** API response shapes unchanged — no
field is added to any of them by this feature; only how those same fields
are laid out on screen changes.

## New view-model concepts (client-side only, not persisted)

### `AdminSection` (admin page tab-shell, US3)

| Value | Displays |
|---|---|
| `courts` | 場地列表、QR Code/連結顯示、新增/刪除場地 |
| `schedule` | 賽程控制（Next Round/Auto Next Round、各場地比分控制區塊） |
| `roster` | 輪替名單 |
| `name` | 團名編輯 |
| `access` | 管理權限資訊（組團編號、管理 PIN 碼、重新產生 PIN 碼） |
| `settings` | 管理員設定（比賽模式、排程機制、解散） |

Held as a single `Signal<AdminSection>` on `AdminPageComponent`, defaulting
to `'courts'`. Not a route param (Decision 2, research.md) — purely
client-side view state, never serialized.

### `FriendshipStatus` (already defined, reused verbatim)

`'none' | 'pending_outgoing' | 'pending_incoming' | 'friends'` — from
`specs/006-member-friends/data-model.md`'s `SearchMemberResponse.friendship_status`.
This feature's `friend-add` screen switches its button/label purely on this
existing enum; no new states are introduced.

## Summary

Every entity this feature touches was defined by a prior spec (001, 005,
006, 007, 008, 009). This spec's own contribution to "data" is nothing more
than the one client-side `AdminSection` enum above — everything else is
either presentation of already-existing API shapes, or the first
implementation of already-fully-specified endpoints (see contracts/).
