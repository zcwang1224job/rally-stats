# Quickstart: 新增英文語系

Validation scenarios mirroring spec.md's acceptance scenarios. Run against
local Docker Compose (`cd infra && docker compose up -d --build web api`).

## Prerequisites

- Local stack running, `en.json` and the backend `SUPPORTED_LANGUAGES`
  change deployed (see contracts/language-api.md, data-model.md).
- One test member account (verified), one anonymous browser session
  (private/incognito window).

## Scenario 1 — Full-app translation coverage (US1, FR-001/FR-004)

1. Open the app anonymously. Confirm zh-TW is shown by default (FR-005).
2. Use the global switcher (nav-shell) to switch to English.
3. Visit at least 5 distinct screens (home, login, create-group, scoreboard,
   member settings). Confirm no residual Traditional Chinese text.
4. Trigger a backend-validation error (e.g. wrong password on login).
   Confirm the error message renders in English, not a raw error code and
   not Chinese (FR-004).
5. **Expected**: SC-001 — ≥90% spot-checked text is English; SC-002 —
   switch takes effect within 2s, no page reload required.

## Scenario 2 — Anonymous/no-nav-shell routes have their own switcher (FR-003a)

1. Open a scoreboard or control-panel URL directly (no login) — e.g. a
   `/scoreboard/:courtToken` link.
2. Confirm a switcher is visible even before/without a valid court link
   (i.e., also visible during the loading/invalidated/error states, not
   only after a court loads) — per plan.md's placement decision (above the
   `@if (linkInvalidated()) {...}` chain).
3. Switch to English; confirm the switcher doesn't crowd or shrink the
   score display (Edge Case, spec.md:62).

## Scenario 3 — Guest choice vs. account preference precedence (US2#3, FR-003b)

1. As an anonymous guest, switch to English.
2. Log in with a member account whose stored `language_preference` is
   `zh-TW` (never changed).
3. **Expected**: the app shows zh-TW immediately after login (account wins,
   no flicker to English first).
4. Use the global switcher again while logged in to pick English.
5. Log out. **Expected**: browser still shows English (US2#4 — logout
   doesn't reset to a default).
6. Log back in with the same account. **Expected**: shows English (FR-003c
   — the earlier switch synced back to `language_preference`).

## Scenario 4 — Cross-device sync (US2#2, FR-007 — existing 022 behavior, re-verify)

1. Logged-in member sets language to English on device/browser A via the
   global switcher.
2. Log into the same account on a fresh browser session B.
3. **Expected**: B shows English without B ever touching a switcher.

## Scenario 5 — New registration seeds from guest choice (US2#5, FR-009)

1. As an anonymous guest, switch to English.
2. Register a brand-new account.
3. **Expected**: immediately after registration (and after email
   verification / first login), the account's language is English — not
   reset to the zh-TW default.

## Scenario 6 — Transactional emails follow language preference (US1#6, FR-010, SC-001a)

1. Set a test member's `language_preference` to English (via settings or
   the global switcher).
2. Trigger a password-reset email (forgot-password flow) and a
   verification email (new registration with guest language = English, or
   resend-verification while `language_preference` = English).
3. **Expected**: both emails' subject and body are in English. Repeat with
   `language_preference` = `zh-TW` and confirm unchanged existing Chinese
   text (no regression).

## Scenario 7 — FR-008: each language shows its own name

1. Open the 個人設定 → 基本設定 language dropdown. Confirm it lists
   "繁體中文" and "English" (not the same label repeated for both options).
2. Open the new global switcher. Confirm the same per-option labeling.

## Regression checks

- Existing zh-TW-only users who never touch a switcher see zero visible
  change (SC-004) — spot-check the same 5 screens from Scenario 1 without
  switching language.
- Full test suites green: backend `pytest` + `ruff check` + `mypy --strict`;
  frontend `ng lint` + `ng build --configuration development` +
  `ng test --watch=false`.
